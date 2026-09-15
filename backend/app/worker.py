"""Celery worker for background reconciliation (SRS section 54).

Run alongside the API:

    celery -A app.worker.celery_app worker --beat --loglevel=info

The in-process reconciliation loop and this Celery worker are both safe to run
together because reconciliation claims rows with FOR UPDATE SKIP LOCKED.
"""
from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("finpay.celery")

celery_app = Celery(
    "finpay",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.update(
    timezone="UTC",
    task_default_queue="finpay",
    beat_schedule={
        "reconcile-pending": {
            "task": "app.worker.reconcile_task",
            "schedule": settings.RECONCILE_INTERVAL_SECONDS,
        },
    },
)


@celery_app.task(name="app.worker.reconcile_task")
def reconcile_task() -> int:
    from app.services.reconciliation_service import run_reconciliation_cycle

    settled = run_reconciliation_cycle()
    if settled:
        logger.info("Celery reconciliation settled %d transaction(s)", settled)
    return settled
