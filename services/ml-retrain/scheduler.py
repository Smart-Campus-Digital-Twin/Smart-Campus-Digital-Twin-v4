"""
Daily retraining scheduler.

Runs train_all() at startup, then every day at 02:00 local time.
On error, sleeps 1 hour and retries. Never crashes the pod.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from retrain import train_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("scheduler")

RUN_HOUR_LOCAL = 2
ERROR_BACKOFF_S = 3600


def _seconds_until_next_run() -> float:
    now = datetime.now()
    target = now.replace(hour=RUN_HOUR_LOCAL, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    log.info("ML retrain scheduler started")
    while True:
        try:
            log.info("Running train_all()")
            train_all()
            log.info("train_all() completed")
        except Exception as exc:
            log.exception("train_all() failed: %s", exc)
            time.sleep(ERROR_BACKOFF_S)
            continue
        wait_s = _seconds_until_next_run()
        log.info("Next run in %.1f hours", wait_s / 3600)
        time.sleep(wait_s)


if __name__ == "__main__":
    main()
