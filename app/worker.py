import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.services.reconciliation_service import run_reconciliation

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def reconciliation_job():
    logger.info("Executing periodic ledger reconciliation scan...")
    db = SessionLocal()
    try:
        results = run_reconciliation(db)
        logger.info("Periodic reconciliation scan completed: %s", results)
    except Exception as exc:
        logger.exception("Error during periodic reconciliation scan: %s", exc)
    finally:
        db.close()


def start_scheduler():
    if not settings.ENABLE_SCHEDULER:
        logger.info("APScheduler is disabled via configuration.")
        return

    if not scheduler.running:
        scheduler.add_job(
            reconciliation_job,
            trigger=IntervalTrigger(seconds=settings.RECONCILIATION_INTERVAL_SECONDS),
            id="reconciliation_job",
            name="Ledger Journal Reconciliation",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(
            "APScheduler started: reconciliation job scheduled every %d seconds.",
            settings.RECONCILIATION_INTERVAL_SECONDS,
        )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
