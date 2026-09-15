import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.models.billing import BillPayment
from app.models.transaction import Transaction, TransactionStatus
from app.models.wallet import LedgerEntry
from app.services import wallet_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_transaction, emit_to_user

logger = get_logger("finpay.reconcile")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _provider_inquiry(txn: Transaction, db: Session) -> str:
    """Mock provider status inquiry. Returns SUCCESS or FAILED.

    A meter ending in 4444 models a genuinely failed operation; otherwise the
    payment actually completed at the provider despite the earlier timeout.
    """
    bill = (
        db.query(BillPayment).filter(BillPayment.transaction_id == txn.id).one_or_none()
    )
    meter = bill.meter_number if bill else ""
    if meter.endswith("4444"):
        return "FAILED"
    return "SUCCESS"


def _settle_success(db: Session, txn: Transaction) -> None:
    wallet = wallet_service.get_wallet(db, txn.user_id)
    charge = txn.amount + txn.fee
    if wallet.balance < charge:
        _settle_failed(db, txn, "Insufficient balance at reconciliation.")
        return
    txn.provider_reference = txn.provider_reference or ("prov_" + uuid.uuid4().hex[:12])
    balance = wallet_service.apply_ledger(
        db, wallet, "DEBIT", charge, txn.id, txn.description
    )
    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                TransactionStatus.PENDING.value,
                                TransactionStatus.SUCCESS.value,
                                {"reconciled": True, "balance_after": balance})
    notif = create_notification(
        db, user_id=txn.user_id, type="BILL_PAYMENT_SUCCESS",
        title="Payment Successful",
        message=f"Your payment of {txn.amount / 100:,.2f} {txn.currency} was confirmed.",
        priority="HIGH", data={"transaction_id": txn.id, "reconciled": True},
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
    txn.status = TransactionStatus.FAILED.value
    txn.failure_reason = reason
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    wallet_service.record_event(db, txn, "TRANSACTION_FAILED",
                                TransactionStatus.PENDING.value,
                                TransactionStatus.FAILED.value,
                                {"reconciled": True, "reason_code": "PROVIDER_FAILED"})
    notif = create_notification(
        db, user_id=txn.user_id, type="BILL_PAYMENT_FAILED", title="Payment Failed",
        message="Your pending payment could not be completed and was not charged.",
        priority="HIGH", data={"transaction_id": txn.id, "reconciled": True},
    )
    db.commit()
    db.refresh(txn)
    emit_to_transaction(txn.id, "transaction:failed", txn.user_id,
                        {"transaction_id": txn.id, "status": txn.status})
    emit_to_user(txn.user_id, "TRANSACTION_FAILED", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "reason_code": "PROVIDER_FAILED", "retryable": True, "reconciled": True,
    })
    deliver_notification(notif)


def _reconcile_one(db: Session, txn: Transaction) -> None:
    txn.reconcile_attempts += 1
    outcome = _provider_inquiry(txn, db)
    if outcome == "SUCCESS":
        _settle_success(db, txn)
    else:
        _settle_failed(db, txn, "The provider reported the payment as failed.")


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
            _reconcile_one(db, txn)  # commits, releasing the row lock
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
            _reconcile_one(db, txn)
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
