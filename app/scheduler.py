"""Worker entrypoint: one APScheduler job per agent, first runs staggered after boot."""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import settings
from .db import init_db
from .orchestrator import build_agents, run_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main():
    init_db()
    sched = BlockingScheduler(timezone=settings.timezone)
    for i, (name, (agent, cfg)) in enumerate(build_agents().items()):
        common = dict(args=[name, agent], id=name, max_instances=1, coalesce=True)
        if "cron_hour" in cfg:
            sched.add_job(run_sync, "cron", hour=cfg["cron_hour"], minute=cfg.get("cron_minute", 0), **common)
        else:
            first = datetime.now(sched.timezone) + timedelta(seconds=30 + 60 * i)
            sched.add_job(run_sync, "interval", minutes=cfg.get("every_min", 60), next_run_time=first, **common)
        logging.info("scheduled agent %s (%s)", name, cfg["type"])
    sched.start()


if __name__ == "__main__":
    main()
