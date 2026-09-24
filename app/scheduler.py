"""Worker entrypoint: one APScheduler job per agent, first runs staggered after boot."""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

from . import prefs
from .config import settings
from .db import init_db
from .orchestrator import build_agents, run_sync
from .preflight import quiet_http_logs

RESCHEDULE_EVERY_MIN = 15

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
quiet_http_logs()


def main():
    init_db()
    sched = BlockingScheduler(timezone=settings.timezone)
    for i, (name, (agent, cfg)) in enumerate(build_agents().items()):
        common = dict(args=[name, agent], id=name, max_instances=1, coalesce=True)
        if "cron_hour" in cfg:
            hour = prefs.digest_hour(cfg["cron_hour"]) if cfg.get("type") == "curator" else cfg["cron_hour"]
            sched.add_job(run_sync, "cron", hour=hour, minute=cfg.get("cron_minute", 0), **common)
        else:
            first = datetime.now(sched.timezone) + timedelta(seconds=30 + 60 * i)
            sched.add_job(run_sync, "interval", minutes=cfg.get("every_min", 60), next_run_time=first, **common)
        logging.info("scheduled agent %s (%s)", name, cfg["type"])
    sched.add_job(follow_digest_time, "interval", minutes=RESCHEDULE_EVERY_MIN,
                  args=[sched], id="digest-time", max_instances=1, coalesce=True)
    sched.start()


def follow_digest_time(sched):
    """You can change the summary time from the ⚙️ buttons; this picks that up without a restart."""
    for name, (_, cfg) in build_agents().items():
        if cfg.get("type") != "curator" or "cron_hour" not in cfg:
            continue
        job = sched.get_job(name)
        wanted = prefs.digest_hour(cfg["cron_hour"])
        if job and str(job.trigger.fields[job.trigger.FIELD_NAMES.index("hour")]) != str(wanted):
            sched.reschedule_job(name, trigger="cron", hour=wanted,
                                 minute=cfg.get("cron_minute", 0))
            logging.info("daily summary moved to %02d:00", wanted)


if __name__ == "__main__":
    main()
