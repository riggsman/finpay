import asyncio
import uuid
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.routers import (
    auth,
    bill_payments,
    dashboard,
    kyc,
    notifications,
    security,
    services,
    social,
    support,
    transactions,
    users,
    wallet,
)
from app.websocket.socket import set_loop, sio

configure_logging()
logger = get_logger("finpay.main")


async def _reconciliation_worker():
    """Periodically settle transactions left pending by provider timeouts."""
    from app.services.reconciliation_service import run_reconciliation_cycle

    while True:
        try:
            await asyncio.sleep(settings.RECONCILE_INTERVAL_SECONDS)
            settled = await asyncio.to_thread(run_reconciliation_cycle)
            if settled:
                logger.info("Reconciliation worker settled %d transaction(s)", settled)
        except asyncio.CancelledError:  # pragma: no cover
            break
        except Exception:  # pragma: no cover - keep the worker alive
            logger.exception("Reconciliation cycle error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Capture the running loop so sync request handlers can emit socket events.
    set_loop(asyncio.get_running_loop())
    logger.info("FinPay backend started (env=%s)", settings.ENVIRONMENT)
    worker = None
    if settings.RECONCILE_WORKER_ENABLED:
        worker = asyncio.create_task(_reconciliation_worker())
        logger.info("Reconciliation worker started (interval=%ss)",
                    settings.RECONCILE_INTERVAL_SECONDS)
    yield
    if worker:
        worker.cancel()
    logger.info("FinPay backend shutting down")


app = FastAPI(title=f"{settings.APP_NAME} API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = "req_" + uuid.uuid4().hex[:16]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": settings.APP_NAME}


api = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api)
app.include_router(users.router, prefix=api)
app.include_router(security.router, prefix=api)
app.include_router(kyc.router, prefix=api)
app.include_router(wallet.router, prefix=api)
app.include_router(transactions.router, prefix=api)
app.include_router(dashboard.router, prefix=api)
app.include_router(notifications.router, prefix=api)
app.include_router(services.router, prefix=api)
app.include_router(bill_payments.router, prefix=api)
app.include_router(support.router, prefix=api)
app.include_router(social.router, prefix=api)

# Wrap the FastAPI app with the Socket.IO ASGI app so both share one server.
asgi = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="socket.io")
