"""
Scheduler for daily automated analysis runs.
Uses APScheduler to trigger analysis at configured times.
"""
from datetime import datetime
import pytz
import structlog

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


def get_scheduler(blocking: bool = True):
    """Get scheduler instance.

    Args:
        blocking: Use BlockingScheduler (for standalone) or BackgroundScheduler

    Returns:
        Scheduler instance
    """
    if blocking:
        return BlockingScheduler()
    return BackgroundScheduler()


def setup_daily_schedule(scheduler, run_func, job_id: str = "daily_analysis"):
    """Set up daily analysis job.

    Args:
        scheduler: APScheduler instance
        run_func: Function to run (main analysis)
        job_id: Unique job identifier
    """
    tz = pytz.timezone(settings.analysis_timezone)

    trigger = CronTrigger(
        hour=settings.analysis_hour,
        minute=settings.analysis_minute,
        timezone=tz
    )

    scheduler.add_job(
        run_func,
        trigger=trigger,
        id=job_id,
        name="Daily NBA Prop Analysis",
        replace_existing=True
    )

    logger.info(
        "scheduled_daily_analysis",
        time=f"{settings.analysis_hour}:{settings.analysis_minute:02d}",
        timezone=settings.analysis_timezone
    )


def setup_injury_update_schedule(scheduler, run_func, job_id: str = "injury_update"):
    """Set up late injury update check.

    Args:
        scheduler: APScheduler instance
        run_func: Function to run
        job_id: Unique job identifier
    """
    tz = pytz.timezone(settings.analysis_timezone)

    # Run at 5 PM ET for late injury updates
    trigger = CronTrigger(
        hour=17,
        minute=0,
        timezone=tz
    )

    scheduler.add_job(
        run_func,
        trigger=trigger,
        id=job_id,
        name="Injury Update Check",
        replace_existing=True
    )

    logger.info("scheduled_injury_update", time="17:00", timezone=settings.analysis_timezone)


def run_scheduler():
    """Run the scheduler (blocking mode).

    This is the main entry point for the scheduled service.
    """
    from main import run_analysis, check_injury_updates

    scheduler = get_scheduler(blocking=True)

    # Set up jobs
    setup_daily_schedule(scheduler, run_analysis)
    setup_injury_update_schedule(scheduler, check_injury_updates)

    logger.info("scheduler_starting")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_stopped")
        scheduler.shutdown()


def run_now(run_func):
    """Run analysis immediately (manual trigger).

    Args:
        run_func: Analysis function to run
    """
    logger.info("manual_run_triggered", time=datetime.now().isoformat())
    run_func()


if __name__ == "__main__":
    run_scheduler()
