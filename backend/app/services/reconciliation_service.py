import datetime as dt
import uuid

from sqlalchemy import or_
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

    return txn.type in (
        "ADD_MONEY",
        "WITHDRAW",
        "MONEY_REQUEST_COLLECT",
        "CAMPAY_COLLECT",
        "CAMPAY_WITHDRAW",
    ) and is_campay_reference(txn.provider_reference)



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
            endpoint=(
                "collect"
                if txn.type in ("ADD_MONEY", "MONEY_REQUEST_COLLECT", "CAMPAY_COLLECT")
                else "withdraw"
            ),
            notify=False,
        )

    if txn.type in ("ADD_MONEY", "MONEY_REQUEST_COLLECT"):
        from app.services import social_service

        money_req = social_service.find_request_by_collect_txn(db, txn.id)
        if money_req or txn.type == "MONEY_REQUEST_COLLECT":
            if outcome == "SUCCESS":
                social_service.settle_money_request_campay_success(db, txn)
            else:
                social_service.settle_money_request_campay_failed(
                    db, txn, reason or "Mobile money payment failed."
                )
        elif outcome == "SUCCESS":
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
    elif txn.type in ("CAMPAY_COLLECT", "CAMPAY_WITHDRAW"):
        # Trace-only Campay rows (admin sandbox) — update status, no wallet move.
        _settle_campay_trace_only(db, txn, outcome, reason)
    else:
        return False

    payment = campay_payment_service.get_for_transaction(db, txn.id)
    if payment:
        campay_payment_service.notify_parties(db, payment, transaction=txn)
        db.commit()
    return True


def _settle_campay_trace_only(
    db: Session,
    txn: Transaction,
    outcome: str,
    reason: str | None = None,
) -> None:
    prev = txn.status
    if outcome == "SUCCESS":
        txn.status = TransactionStatus.SUCCESS.value
        txn.failure_reason = None
        event = "TRANSACTION_SUCCESS"
        new = TransactionStatus.SUCCESS.value
    else:
        txn.status = TransactionStatus.FAILED.value
        txn.failure_reason = (reason or "Provider reported failure.")[:255]
        event = "TRANSACTION_FAILED"
        new = TransactionStatus.FAILED.value
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    wallet_service.record_event(db, txn, event, prev, new, {"provider": "campay", "trace_only": True})


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
            .filter(
                Transaction.type.in_(
                    (
                        "ADD_MONEY",
                        "WITHDRAW",
                        "MONEY_REQUEST_COLLECT",
                        "CAMPAY_COLLECT",
                        "CAMPAY_WITHDRAW",
                    )
                )
            )
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


NON_TERMINAL_STATUSES = frozenset({
    TransactionStatus.CREATED.value,
    TransactionStatus.PENDING.value,
    TransactionStatus.PROCESSING.value,
})


def _status_str(value) -> str:
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else str(value)


def describe_provider_action(mapped: str, finpay_status: str, txn_type: str) -> dict:
    """Explain what admin should do after a Campay status check."""
    mapped = (mapped or "PENDING").upper()
    finpay = (finpay_status or "").upper()
    t = (txn_type or "").upper()

    if mapped == "PENDING":
        return {
            "needs_reconciliation": False,
            "action_required": "Campay is still processing. Re-check later — no FinPay update yet.",
            "action_label": None,
        }

    if mapped == "SUCCESS" and finpay in NON_TERMINAL_STATUSES:
        if t in ("ADD_MONEY", "MONEY_REQUEST_COLLECT", "CAMPAY_COLLECT"):
            action = (
                "Reconcile to credit the beneficiary wallet and mark this FinPay "
                "transaction SUCCESS."
            )
        elif t in ("WITHDRAW", "CAMPAY_WITHDRAW"):
            action = "Reconcile to finalize the withdrawal and mark FinPay SUCCESS."
        else:
            action = "Reconcile to apply Campay SUCCESS and update the FinPay status."
        return {
            "needs_reconciliation": True,
            "action_required": action,
            "action_label": "Reconcile & credit",
        }

    if mapped == "FAILED" and finpay in NON_TERMINAL_STATUSES:
        return {
            "needs_reconciliation": True,
            "action_required": (
                "Reconcile to mark this FinPay transaction FAILED "
                "(no wallet credit)."
            ),
            "action_label": "Reconcile as failed",
        }

    if mapped == "SUCCESS" and finpay == TransactionStatus.SUCCESS.value:
        return {
            "needs_reconciliation": False,
            "action_required": "Already in sync — FinPay is SUCCESS. No action required.",
            "action_label": None,
        }

    if mapped == "FAILED" and finpay == TransactionStatus.FAILED.value:
        return {
            "needs_reconciliation": False,
            "action_required": "Already in sync — FinPay is FAILED. No action required.",
            "action_label": None,
        }

    return {
        "needs_reconciliation": True,
        "action_required": (
            f"Status mismatch: Campay is {mapped} but FinPay is {finpay}. "
            "Review carefully, then reconcile if the provider result should win."
        ),
        "action_label": "Force reconcile",
    }


def admin_reconcile_transaction(db: Session, txn: Transaction) -> tuple[bool, str, dict]:
    """Re-query Campay and settle the FinPay ledger for admin reconciliation.

    Returns (settled, mapped_status, provider_payload).
    """
    from app.integrations.campay import (
        campay_credentials_ready,
        get_campay_client,
        is_campay_reference,
        map_campay_status,
    )

    if not campay_credentials_ready():
        from app.core.exceptions import AppError

        raise AppError(
            "Campay is not configured. Set CAMPAY_USERNAME and CAMPAY_PASSWORD.",
            code="CAMPAY_NOT_CONFIGURED",
            status_code=503,
        )
    if not txn.provider_reference or not is_campay_reference(txn.provider_reference):
        from app.core.exceptions import ValidationError

        raise ValidationError(
            "This transaction has no Campay provider reference to reconcile.",
            code="NO_PROVIDER_REFERENCE",
        )

    data = get_campay_client().get_transaction(txn.provider_reference)
    mapped = map_campay_status(data.get("status"))
    if mapped == "PENDING":
        from app.core.exceptions import ValidationError

        raise ValidationError(
            "Campay is still pending — cannot reconcile until SUCCESSFUL or FAILED.",
            code="PROVIDER_STILL_PENDING",
        )

    settled = bool(
        apply_campay_outcome(
            db,
            txn,
            mapped,
            reason=data.get("reason"),
            payload=data,
        )
    )
    if not settled:
        from app.core.exceptions import ValidationError

        raise ValidationError(
            f"Could not settle transaction type {txn.type} from Campay {mapped}.",
            code="RECONCILE_UNSUPPORTED",
        )
    db.refresh(txn)
    return settled, mapped, data


def _claim_next(db: Session, extra_filters) -> Transaction | None:
    """Claim one pending transaction with FOR UPDATE NOWAIT so that
    concurrent workers (in-process + Celery) never process the same row."""
    q = db.query(Transaction).filter(
        Transaction.pending_reconciliation.is_(True),
        Transaction.status.in_(
            (
                TransactionStatus.PENDING.value,
                TransactionStatus.PROCESSING.value,
            )
        ),
        *extra_filters,
    )
    try:
        return q.order_by(Transaction.id).with_for_update(nowait=True).first()
    except Exception:
        db.rollback()
        return None


def _claim_txn(db: Session, txn_id: int) -> Transaction | None:
    try:
        return (
            db.query(Transaction)
            .filter(
                Transaction.id == txn_id,
                Transaction.pending_reconciliation.is_(True),
                Transaction.status.in_(
                    (
                        TransactionStatus.PENDING.value,
                        TransactionStatus.PROCESSING.value,
                    )
                ),
            )
            .with_for_update(nowait=True)
            .one_or_none()
        )
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
    """Immediately reconcile a user's pending wallet txns and any money-request
    Campay collects they are party to (payer or requester)."""
    from app.models.social import MoneyRequest

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

    # Money-request collects live on the payer's user_id; the requester must
    # still be able to nudge settlement while waiting on PROCESSING.
    open_reqs = (
        db.query(MoneyRequest)
        .filter(
            MoneyRequest.status == "PROCESSING",
            MoneyRequest.collect_transaction_id.isnot(None),
            or_(
                MoneyRequest.payer_id == user_id,
                MoneyRequest.requester_id == user_id,
            ),
        )
        .all()
    )
    for req in open_reqs:
        txn = _claim_txn(db, int(req.collect_transaction_id))
        if txn is None:
            continue
        try:
            if _reconcile_one(db, txn):
                settled += 1
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "Money-request collect reconcile failed for txn=%s req=%s",
                txn.id,
                req.id,
            )
            db.rollback()
    return settled


def run_reconciliation_cycle() -> int:
    """Entry point for the background worker (opens its own session)."""
    db = SessionLocal()
    try:
        return reconcile_pending(db)
    finally:
        db.close()
