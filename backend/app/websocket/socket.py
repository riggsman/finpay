import asyncio

import socketio

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.database import SessionLocal
from app.events.envelope import make_envelope
from app.models.user import User

logger = get_logger("finpay.socket")


def _build_server() -> socketio.AsyncServer:
    client_manager = None
    if settings.use_redis:
        try:
            client_manager = socketio.AsyncRedisManager(settings.REDIS_URL)
            logger.info("Socket.IO using Redis manager at %s", settings.REDIS_URL)
        except Exception as exc:  # pragma: no cover - depends on runtime redis
            logger.warning("Redis manager unavailable, falling back to in-memory: %s", exc)
            client_manager = None
    return socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins=settings.cors_origins_list,
        client_manager=client_manager,
        logger=False,
        engineio_logger=False,
    )


sio = _build_server()

# The main event loop, captured on startup, so synchronous request handlers
# (which run in a threadpool) can schedule socket emissions safely.
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _resolve_user(user_id: int) -> User | None:
    db = SessionLocal()
    try:
        return db.get(User, user_id)
    finally:
        db.close()


def _authenticate(token: str | None) -> int | None:
    if not token:
        return None
    token = token.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except Exception:
        return None
    if payload.get("type") != "access":
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    user = _resolve_user(user_id)
    if not user or not user.is_active:
        return None
    return user_id


@sio.event
async def connect(sid, environ, auth):
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get("token")
    if not token:
        # Fallback to Authorization header / query string
        headers = {k.lower(): v for k, v in (environ.get("headers_raw") or [])}
        token = headers.get("authorization")
    user_id = await asyncio.get_running_loop().run_in_executor(None, _authenticate, token)
    if user_id is None:
        logger.info("Rejected unauthenticated socket connection sid=%s", sid)
        raise socketio.exceptions.ConnectionRefusedError("authentication_failed")
    await sio.save_session(sid, {"user_id": user_id})
    await sio.enter_room(sid, f"user:{user_id}")
    logger.info("Socket connected sid=%s user=%s", sid, user_id)
    await sio.emit(
        "connection:ready",
        make_envelope("connection:ready", user_id, {"status": "CONNECTED"}),
        to=sid,
    )


@sio.event
async def disconnect(sid):
    logger.info("Socket disconnected sid=%s", sid)


@sio.on("transaction:subscribe")
async def transaction_subscribe(sid, data):
    """Allow a client to subscribe to a transaction room it owns."""
    session = await sio.get_session(sid)
    user_id = session.get("user_id")
    transaction_id = (data or {}).get("transaction_id")
    if not transaction_id:
        return {"ok": False, "error": "transaction_id required"}

    def _owns() -> bool:
        from app.models.transaction import Transaction

        db = SessionLocal()
        try:
            txn = db.get(Transaction, int(transaction_id))
            return bool(txn and txn.user_id == user_id)
        except Exception:
            return False
        finally:
            db.close()

    owns = await asyncio.get_running_loop().run_in_executor(None, _owns)
    if not owns:
        return {"ok": False, "error": "forbidden"}
    await sio.enter_room(sid, f"transaction:{transaction_id}")
    return {"ok": True}


@sio.on("transaction:unsubscribe")
async def transaction_unsubscribe(sid, data):
    transaction_id = (data or {}).get("transaction_id")
    if transaction_id:
        await sio.leave_room(sid, f"transaction:{transaction_id}")
    return {"ok": True}


def emit_to_user(user_id: int, event_type: str, data: dict,
                 event_id: str | None = None) -> None:
    """Thread-safe emit to a user's room from synchronous code."""
    envelope = make_envelope(event_type, user_id, data, event_id=event_id)
    _schedule(sio.emit(event_type, envelope, room=f"user:{user_id}"))


def emit_to_transaction(transaction_id: int, event_type: str, user_id: int,
                        data: dict) -> None:
    envelope = make_envelope(event_type, user_id, data)
    _schedule(sio.emit(event_type, envelope, room=f"transaction:{transaction_id}"))


def _schedule(coro) -> None:
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, _loop)
    else:  # pragma: no cover - only during tests without a running loop
        logger.warning("No running event loop; dropping socket emission")
