import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.models.billing import BillPayment
from app.models.transaction import Transaction, TransactionStatus
from app.services import transfers_service, wallet_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_transaction, emit_to_user

logger = get_logger("finpay.reconcile")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _is_campay_txn(txn: Transaction) -> bool:
    from app.integrations.campay import is_campay_reference

    return txn.type in ("ADD_MONEY", "WITHDRAW") and is_campay_reference(
        txn.provider_reference
    )


def _provider_inquiry(txn: Transaction, db: Session) -> tuple[str, dict]:
    """Return (SUCCESS|FAILED|PENDING, provider_payload)."""
    if _is_campay_txn(txn):
        from app.integrations.campay import get_campay_client, map_campay_status
        from app.services import campay_payment_service

        try:
            data = get_campay_client().get_transaction(txn.provider_reference)
        except Exception:
            logger.exception("Campay status inquiry failed for txn=%s", txn.id)
            return "PENDING", {}
        # Persist latest Campay fields without notifying yet (notify after settle).
        campay_payment_service.apply_status_payload(
            db, data, transaction=txn, notify=False
        )
        return map_campay_status(data.get("status")), data

    # Mock bill-pay inquiry. Meter ending in 4444 => FAILED.
    bill = (
        db.query(BillPayment).filter(BillPayment.transaction_id == txn.id).one_or_none()
    )
    meter = bill.meter_number if bill else ""
    if meter.endswith("4444"):
        return "FAILED", {}
    return "SUCCESS", {}


def apply_campay_outcome(
    db: Session,
    txn: Transaction,
    outcome: str,
    reason: str | None = None,
    payload: dict | None = None,
) -> bool:
    """Settle a Campay wallet txn. Returns True if terminal state applied."""
    from app.services import campay_payment_service

    outcome = (outcome or "").upper()
    if outcome == "PENDING":
        return False

    if payload:
        payment = campay_payment_service.apply_status_payload(
            db, payload, transaction=txn, notify=False
        )
        if payment and payment.reason:
            reason = reason or payment.reason
    elif txn.provider_reference:
        # Ensure a payment row exists even if inquiry payload was empty.
        campay_payment_service.apply_status_payload(
            db,
            {
                "reference": txn.provider_reference,
                "status": "SUCCESSFUL" if outcome == "SUCCESS" else "FAILED",
                "reason": reason,
                "external_reference": txn.reference,
            },
            transaction=txn,
            endpoint="collect" if txn.type == "ADD_MONEY" else "withdraw",
            notify=False,
        )

    if txn.type == "ADD_MONEY":
        if outcome == "SUCCESS":
            wallet_service.settle_campay_deposit_success(db, txn)
        else:
            wallet_service.settle_campay_deposit_failed(
                db, txn, reason or "Mobile money payment failed."
            )
    elif txn.type == "WITHDRAW":
        if outcome == "SUCCESS":
            transfers_service.settle_campay_withdraw_success(db, txn)
        else:
            transfers_service.settle_campay_withdraw_failed(
                db, txn, reason or "Withdrawal failed at provider."
            )
    else:
        return False

    payment = campay_payment_service.get_for_transaction(db, txn.id)
    if payment:
        campay_payment_service.notify_parties(db, payment, transaction=txn)
        db.commit()
    return True


def find_txn_for_campay(
    db: Session,
    *,
    campay_reference: str | None = None,
    external_reference: str | None = None,
) -> Transaction | None:
    """Resolve the FinPay wallet txn for a Campay callback.

    Prefer the newest ADD_MONEY/WITHDRAW match. Duplicate provider_reference
    rows (re-tests, polluted DBs) must not crash the webhook with
    MultipleResultsFound — Campay would then keep retrying.
    """
    q = db.query(Transaction)
    if campay_reference:
        txn = (
            q.filter(Transaction.provider_reference == campay_reference)
            .filter(Transaction.type.in_(("ADD_MONEY", "WITHDRAW")))
            .order_by(Transaction.id.desc())
            .first()
        )
        if txn:
            return txn
        txn = (
            db.query(Transaction)
            .filter(Transaction.provider_reference == campay_reference)
            .order_by(Transaction.id.desc())
            .first()
        )
        if txn:
            return txn
    if external_reference:
        return (
            db.query(Transaction)
            .filter(Transaction.reference == external_reference)
            .order_by(Transaction.id.desc())
            .first()
        )
    return None


def _settle_success(db: Session, txn: Transaction) -> None:
    wallet = wallet_service.get_wallet(db, txn.user_id)
    # Prefer the held charge (amount + fee) from confirm time; only debit if missing.
    if not wallet_service.has_debit_for_txn(db, txn.id):
        charge = wallet_service.total_charge(txn)
        if wallet.balance < charge:
            _settle_failed(db, txn, "Insufficient balance at reconciliation.")
            return
        balance = wallet_service.debit_with_fee(db, wallet, txn, txn.description)
    else:
        balance = wallet.balance
    txn.provider_reference = txn.provider_reference or ("prov_" + uuid.uuid4().hex[:12])
    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                TransactionStatus.PENDING.value,
                                TransactionStatus.SUCCESS.value,
                                {"reconciled": True, "balance_after": balance, "fee": txn.fee})
    bill = (
        db.query(BillPayment).filter(BillPayment.transaction_id == txn.id).one_or_none()
    )
    category = (bill.category if bill else None) or (
        txn.type.lower() if txn.type else "electricity"
    )
    notif = create_notification(
        db, user_id=txn.user_id, type="BILL_PAYMENT_SUCCESS",
        title="Payment Successful",
        message=f"Your payment of {txn.amount / 100:,.2f} {txn.currency} was confirmed.",
        priority="HIGH",
        data={"transaction_id": txn.id, "reconciled": True, "category": category, "fee": txn.fee},
    )
    db.commit()
    db.refresh(txn)
    db.refresh(wallet)
    emit_to_transaction(txn.id, "transaction:success", txn.user_id,
                        {"transaction_id": txn.id, "status": txn.status})
    emit_to_user(txn.user_id, "TRANSACTION_SUCCESS", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "amount": txn.amount, "currency": txn.currency, "reconciled": True,
    })
    emit_to_user(txn.user_id, "WALLET_BALANCE_UPDATED",
                 {"balance": balance, "currency": wallet.currency})
    deliver_notification(notif)


def _settle_failed(db: Session, txn: Transaction, reason: str) -> None:
    wallet = wallet_service.get_wallet(db, txn.user_id)
    if wallet_service.has_debit_for_txn(db, txn.id):
        balance = wallet_service.refund_charge(db, wallet, txn)
    else:
        balance = wallet.balance
    txn.status = TransactionStatus.FAILED.value
    txn.failure_reason = reason
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    wallet_service.record_event(db, txn, "TRANSACTION_FAILED",
                                TransactionStatus.PENDING.value,
                                TransactionStatus.FAILED.value,
                                {"reconciled": True, "reason_code": "PROVIDER_FAILED", "refunded": True})
    bill = (
        db.query(BillPayment).filter(BillPayment.transaction_id == txn.id).one_or_none()
    )
    category = (bill.category if bill else None) or (
        txn.type.lower() if txn.type else "electricity"
    )
    notif = create_notification(
        db, user_id=txn.user_id, type="BILL_PAYMENT_FAILED", title="Payment Failed",
        message="Your pending payment could not be completed and was not charged.",
        priority="HIGH",
        data={"transaction_id": txn.id, "reconciled": True, "category": category},
    )
    db.commit()
    db.refresh(txn)
    emit_to_transaction(txn.id, "transaction:failed", txn.user_id,
                        {"transaction_id": txn.id, "status": txn.status})
    emit_to_user(txn.user_id, "TRANSACTION_FAILED", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "reason_code": "PROVIDER_FAILED", "retryable": True, "reconciled": True,
    })
    emit_to_user(txn.user_id, "WALLET_BALANCE_UPDATED",
                 {"balance": balance, "currency": wallet.currency})
    deliver_notification(notif)


def _reconcile_one(db: Session, txn: Transaction) -> bool:
    """Return True when the transaction reached a terminal state."""
    txn.reconcile_attempts += 1
    outcome, payload = _provider_inquiry(txn, db)
    if outcome == "PENDING":
        db.commit()
        return False

    if _is_campay_txn(txn):
        return apply_campay_outcome(db, txn, outcome, payload=payload)

    if outcome == "SUCCESS":
        _settle_success(db, txn)
    else:
        _settle_failed(db, txn, "The provider reported the payment as failed.")
    return True


def _claim_next(db: Session, extra_filters) -> Transaction | None:
    """Claim one pending transaction with FOR UPDATE NOWAIT so that
    concurrent workers (in-process + Celery) never process the same row."""
    q = db.query(Transaction).filter(
        Transaction.pending_reconciliation.is_(True),
        Transaction.status == TransactionStatus.PENDING.value,
        *extra_filters,
    )
    try:
        return q.order_by(Transaction.id).with_for_update(nowait=True).first()
    except Exception:
        db.rollback()
        return None


def reconcile_pending(db: Session, min_age_seconds: float | None = None) -> int:
    """Settle pending-reconciliation transactions older than the threshold,
    one at a time under a row lock. Returns the count settled."""
    if min_age_seconds is None:
        min_age_seconds = settings.RECONCILE_MIN_AGE_SECONDS
    cutoff = _now() - dt.timedelta(seconds=min_age_seconds)
    settled = 0
    while True:
        txn = _claim_next(db, [Transaction.created_at <= cutoff])
        if txn is None:
            break
        try:
            if _reconcile_one(db, txn):
                settled += 1
        except Exception:  # pragma: no cover - defensive
            logger.exception("Reconcile failed for txn=%s", txn.id)
            db.rollback()
            break
    return settled


def reconcile_for_user(db: Session, user_id: int) -> int:
    """Immediately reconcile a specific user's pending transactions (used for
    application-open / network-recovery flows)."""
    settled = 0
    while True:
        txn = _claim_next(db, [Transaction.user_id == user_id])
        if txn is None:
            break
        try:
            if _reconcile_one(db, txn):
                settled += 1
        except Exception:  # pragma: no cover - defensive
            logger.exception("User reconcile failed for txn=%s", txn.id)
            db.rollback()
            break
    return settled


def run_reconciliation_cycle() -> int:
    """Entry point for the background worker (opens its own session)."""
    db = SessionLocal()
    try:
        return reconcile_pending(db)
    finally:
        db.close()
