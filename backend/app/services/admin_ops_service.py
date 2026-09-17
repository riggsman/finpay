"""Back Office helpers: users, profiles, and transaction search."""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.kyc import KycProfile
from app.models.transaction import Transaction
from app.models.user import User
from app.models.wallet import LedgerEntry, Wallet
from app.services import security_service

CREDIT_TYPES = frozenset({
    "ADD_MONEY",
    "TRANSFER_RECEIVED",
    "MONEY_REQUEST_OUT",
})

CAMPAY_TXN_TYPES = frozenset({
    "ADD_MONEY",
    "WITHDRAW",
    "MONEY_REQUEST_COLLECT",
    "CAMPAY_COLLECT",
    "CAMPAY_WITHDRAW",
})

_PHONE_IN_TEXT = re.compile(r"(\+?237\d{9}|\b0?6\d{8}\b)")


def _user_label(user: User | None) -> str:
    if not user:
        return "—"
    return (user.full_name or user.phone or user.email or f"User #{user.id}").strip()


def _user_phone(user: User | None) -> str | None:
    if not user or not user.phone:
        return None
    return user.phone


def _after(desc: str, prefix: str) -> str | None:
    low = (desc or "").lower()
    p = prefix.lower()
    if low.startswith(p):
        value = desc[len(prefix) :].strip()
        return value or None
    return None


def _extract_phone(text: str | None) -> str | None:
    if not text:
        return None
    m = _PHONE_IN_TEXT.search(text)
    return m.group(1) if m else None


def _find_transfer_twin(db: Session | None, txn: Transaction) -> User | None:
    t = (txn.type or "").upper()
    if db is None or t not in {"SEND_MONEY", "TRANSFER_RECEIVED"}:
        return None
    twin_type = "TRANSFER_RECEIVED" if t == "SEND_MONEY" else "SEND_MONEY"
    twin = (
        db.query(Transaction)
        .filter(
            Transaction.type == twin_type,
            Transaction.amount == txn.amount,
            Transaction.id != txn.id,
            Transaction.user_id != txn.user_id,
            Transaction.created_at >= txn.created_at - dt.timedelta(seconds=30),
            Transaction.created_at <= txn.created_at + dt.timedelta(seconds=30),
        )
        .order_by(Transaction.id.asc())
        .first()
    )
    return db.get(User, twin.user_id) if twin else None


def resolve_method(txn: Transaction) -> str:
    """Normalize funding / rails label: card | bank | momo | wallet | —."""
    t = (txn.type or "").upper()
    desc = (txn.description or "").lower()

    if t in {"MONEY_REQUEST_COLLECT", "CAMPAY_COLLECT", "CAMPAY_WITHDRAW"}:
        return "momo"
    if t == "WITHDRAW":
        return "momo"
    if t == "ADD_MONEY":
        if "mobile money" in desc or "momo" in desc or "mtn" in desc or "orange" in desc:
            return "momo"
        if "card" in desc or "visa" in desc or "mastercard" in desc:
            return "card"
        if "bank" in desc:
            return "bank"
        return "—"
    if t in {"SEND_MONEY", "TRANSFER_RECEIVED", "MONEY_REQUEST_OUT", "MONEY_REQUEST_IN"}:
        if "mobile money" in desc:
            return "momo"
        return "wallet"
    if t in {"ELECTRICITY", "AIRTIME", "DATA", "GAS", "WATER", "TV", "INTERNET"}:
        return "wallet"
    return "—"


def resolve_parties(
    db: Session | None,
    txn: Transaction,
    user: User,
) -> tuple[str, str]:
    """Legacy (sender, receiver) name labels — kept for callers."""
    info = resolve_txn_display(db, txn, user)
    return info["sender"], info["receiver"]


def resolve_txn_display(
    db: Session | None,
    txn: Transaction,
    user: User,
) -> dict[str, str | None]:
    """Sender/receiver names + phones, and payment method for admin tables.

    Sender is only the party that sends/funds the operation — never the method
    label (card/bank/momo live in ``method``).
    """
    self_label = _user_label(user)
    self_phone = _user_phone(user)
    desc = (txn.description or "").strip()
    t = (txn.type or "").upper()
    twin = _find_transfer_twin(db, txn)
    method = resolve_method(txn)

    empty = {
        "sender": "—",
        "sender_phone": None,
        "receiver": "—",
        "receiver_phone": None,
        "method": method,
    }

    if t == "ADD_MONEY":
        # External rail funds the wallet owner — no FinPay "sender" person.
        momo_phone = _extract_phone(desc) if method == "momo" else None
        return {
            "sender": "External",
            "sender_phone": momo_phone,
            "receiver": self_label,
            "receiver_phone": self_phone,
            "method": method,
        }

    if t == "WITHDRAW":
        dest = _after(desc, "Withdrawal to ") or "External account"
        return {
            "sender": self_label,
            "sender_phone": self_phone,
            "receiver": dest,
            "receiver_phone": _extract_phone(desc) or _extract_phone(dest),
            "method": method,
        }

    if t == "SEND_MONEY":
        dest_name = _user_label(twin) if twin else (_after(desc, "Transfer to ") or "Recipient")
        return {
            "sender": self_label,
            "sender_phone": self_phone,
            "receiver": dest_name,
            "receiver_phone": _user_phone(twin) or _extract_phone(desc),
            "method": method,
        }

    if t == "TRANSFER_RECEIVED":
        src_name = _user_label(twin) if twin else (_after(desc, "Transfer from ") or "Sender")
        return {
            "sender": src_name,
            "sender_phone": _user_phone(twin) or _extract_phone(desc),
            "receiver": self_label,
            "receiver_phone": self_phone,
            "method": method,
        }

    if t == "MONEY_REQUEST_OUT":
        # Funds will come from payer → requester (this row's user).
        payer_name = _after(desc, "Request to ") or "Payer"
        payer_phone = None
        if db is not None:
            from app.models.social import MoneyRequest

            req = (
                db.query(MoneyRequest)
                .filter(MoneyRequest.transaction_id == txn.id)
                .one_or_none()
            )
            if req:
                payer = db.get(User, req.payer_id)
                payer_name = _user_label(payer) or payer_name
                payer_phone = _user_phone(payer)
        return {
            "sender": payer_name,
            "sender_phone": payer_phone or _extract_phone(desc),
            "receiver": self_label,
            "receiver_phone": self_phone,
            "method": method,
        }

    if t == "MONEY_REQUEST_IN":
        # This row's user is the payer (sender of funds).
        requester_name = _after(desc, "Request from ") or "Requester"
        requester_phone = None
        if db is not None:
            from app.models.social import MoneyRequest

            req = (
                db.query(MoneyRequest)
                .filter(MoneyRequest.payer_transaction_id == txn.id)
                .one_or_none()
            )
            if req:
                requester = db.get(User, req.requester_id)
                requester_name = _user_label(requester) or requester_name
                requester_phone = _user_phone(requester)
        return {
            "sender": self_label,
            "sender_phone": self_phone,
            "receiver": requester_name,
            "receiver_phone": requester_phone or _extract_phone(desc),
            "method": method,
        }

    if t in {"MONEY_REQUEST_COLLECT", "CAMPAY_COLLECT"}:
        return {
            "sender": "External",
            "sender_phone": _extract_phone(desc),
            "receiver": self_label,
            "receiver_phone": self_phone,
            "method": method,
        }

    if t == "CAMPAY_WITHDRAW":
        return {
            "sender": self_label,
            "sender_phone": self_phone,
            "receiver": "Mobile money",
            "receiver_phone": _extract_phone(desc),
            "method": method,
        }

    if t in {"MONEY_REQUEST_PAID", "REQUEST_PAID"}:
        other = _after(desc, "Paid request to ") or _after(desc, "Payment to ") or "Requester"
        return {
            "sender": self_label,
            "sender_phone": self_phone,
            "receiver": other,
            "receiver_phone": _extract_phone(desc),
            "method": method,
        }

    # Bill / top-up style: "Category • Provider • target"
    if "•" in desc:
        parts = [p.strip() for p in desc.split("•") if p.strip()]
        merchant = " • ".join(parts[1:]) if len(parts) > 1 else parts[0]
        return {
            "sender": self_label,
            "sender_phone": self_phone,
            "receiver": merchant or "Merchant",
            "receiver_phone": _extract_phone(desc),
            "method": method,
        }

    if t in CREDIT_TYPES:
        return {
            "sender": "External",
            "sender_phone": None,
            "receiver": self_label,
            "receiver_phone": self_phone,
            "method": method,
        }

    return {
        **empty,
        "sender": self_label,
        "sender_phone": self_phone,
        "receiver": desc or "Merchant",
        "receiver_phone": _extract_phone(desc),
    }


def account_number_for(wallet_id: int | None) -> str | None:
    if wallet_id is None:
        return None
    return f"FP{int(wallet_id):08d}"


def parse_account_number(value: str) -> int | None:
    raw = (value or "").strip().upper().replace(" ", "")
    if not raw:
        return None
    if raw.startswith("FP") and raw[2:].isdigit():
        return int(raw[2:])
    if raw.isdigit():
        return int(raw)
    return None


def txn_direction(txn_type: str) -> str:
    return "IN" if txn_type in CREDIT_TYPES else "OUT"


def can_verify_provider(txn: Transaction) -> bool:
    """True when admin can query Campay and optionally settle this row."""
    from app.integrations.campay import is_campay_reference

    if (txn.type or "").upper() not in CAMPAY_TXN_TYPES and not is_campay_reference(
        txn.provider_reference
    ):
        return False
    return bool(txn.provider_reference) and is_campay_reference(txn.provider_reference)


def list_users(
    db: Session,
    *,
    user_id: int | None = None,
    phone: str | None = None,
    name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[User]:
    q = db.query(User).filter(User.is_admin.is_(False))
    if user_id is not None:
        q = q.filter(User.id == user_id)
    if phone:
        q = q.filter(User.phone.ilike(f"%{phone.strip()}%"))
    if name:
        term = f"%{name.strip()}%"
        q = q.filter(
            or_(
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                func.concat(User.first_name, " ", User.last_name).ilike(term),
            )
        )
    return q.order_by(User.id.desc()).offset(offset).limit(limit).all()


def get_user_profile(db: Session, user_id: int) -> dict:
    user = db.get(User, user_id)
    if not user or user.is_admin:
        raise NotFoundError("User not found.", code="USER_NOT_FOUND")

    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).one_or_none()
    kyc = db.query(KycProfile).filter(KycProfile.user_id == user.id).one_or_none()
    per_txn_limit, daily_limit = security_service.effective_limits(db, user)

    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name or None,
        "email": user.email,
        "phone": user.phone,
        "status": user.status.value if hasattr(user.status, "value") else str(user.status),
        "phone_verified": user.phone_verified,
        "email_verified": user.email_verified,
        "is_admin": user.is_admin,
        "per_txn_limit": per_txn_limit,
        "daily_limit": daily_limit,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
        "account_number": account_number_for(wallet.id) if wallet else None,
        "wallet": (
            {
                "id": wallet.id,
                "balance": wallet.balance,
                "currency": wallet.currency,
                "account_number": account_number_for(wallet.id),
            }
            if wallet
            else None
        ),
        "kyc": (
            {
                "id": kyc.id,
                "status": kyc.status,
                "first_name": kyc.first_name,
                "last_name": kyc.last_name,
                "date_of_birth": kyc.date_of_birth,
                "address_line": kyc.address_line,
                "city": kyc.city,
                "country": kyc.country,
                "id_type": kyc.id_type,
                "id_number": kyc.id_number,
                "id_document_ref": kyc.id_document_ref,
                "id_document_back_ref": kyc.id_document_back_ref,
                "selfie_ref": kyc.selfie_ref,
                "rejection_reason": kyc.rejection_reason,
                "submitted_at": kyc.submitted_at,
                "reviewed_at": kyc.reviewed_at,
            }
            if kyc
            else None
        ),
    }


def list_transactions(
    db: Session,
    *,
    user_id: int | None = None,
    phone: str | None = None,
    account_number: str | None = None,
    type_: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[Transaction, User, Wallet | None]]:
    q = (
        db.query(Transaction, User, Wallet)
        .join(User, User.id == Transaction.user_id)
        .outerjoin(Wallet, Wallet.user_id == User.id)
        .filter(User.is_admin.is_(False))
    )

    if user_id is not None:
        q = q.filter(Transaction.user_id == user_id)
    if phone:
        q = q.filter(User.phone.ilike(f"%{phone.strip()}%"))
    if account_number:
        wallet_id = parse_account_number(account_number)
        phone_like = f"%{account_number.strip()}%"
        clauses = [User.phone.ilike(phone_like)]
        if wallet_id is not None:
            clauses.append(Wallet.id == wallet_id)
            clauses.append(cast(Wallet.id, String).ilike(f"%{wallet_id}%"))
        q = q.filter(or_(*clauses))
    if type_:
        q = q.filter(Transaction.type == type_.upper())
    if status:
        q = q.filter(Transaction.status == status.upper())
    if direction:
        d = direction.upper()
        if d in ("IN", "CREDIT", "INBOUND"):
            q = q.filter(Transaction.type.in_(tuple(CREDIT_TYPES)))
        elif d in ("OUT", "DEBIT", "OUTBOUND"):
            q = q.filter(~Transaction.type.in_(tuple(CREDIT_TYPES)))

    rows = q.order_by(Transaction.id.desc()).offset(offset).limit(limit).all()
    return rows


def ledger_direction_for(db: Session, txn: Transaction) -> str | None:
    entry = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.transaction_id == txn.id)
        .order_by(LedgerEntry.id.asc())
        .first()
    )
    if not entry:
        return None
    return "IN" if entry.direction == "CREDIT" else "OUT"
