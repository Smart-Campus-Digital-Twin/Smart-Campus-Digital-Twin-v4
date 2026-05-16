#!/usr/bin/env python3
"""
Smart Campus ML Retraining Daemon
=================================
Runs the bootstrap_training.py script once every 24 hours.
"""

import time
import subprocess
import os
import sys
from datetime import datetime, timedelta
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("retrain_daemon")

BOOTSTRAP_SCRIPT = os.path.join(os.path.dirname(__file__), "bootstrap_training.py")

def run_retraining():
    logger.info("Starting scheduled retraining...")
    try:
        # Run bootstrap_training.py
        result = subprocess.run(
            [sys.executable, BOOTSTRAP_SCRIPT],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ},
            cwd=os.path.dirname(__file__),
        )
        logger.info("Retraining successful!")
        if result.stdout:
            logger.debug("Retraining stdout:\n%s", result.stdout)
        if result.stderr:
            logger.debug("Retraining stderr:\n%s", result.stderr)
    except subprocess.CalledProcessError as e:
        logger.error("Retraining failed with exit code %s", e.returncode)
        logger.error("Error stdout: %s", getattr(e, "stdout", ""))
        logger.error("Error stderr: %s", getattr(e, "stderr", ""))
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

def main():
    logger.info("Smart Campus ML Retraining Daemon started.")
    logger.info(f"Retraining interval: 24 hours")
    
    # Run once at startup
    run_retraining()
    
    while True:
        # Calculate time until next run (e.g., 02:00 AM next day)
        now = datetime.now()
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        
        wait_seconds = (next_run - now).total_seconds()
        logger.info(f"Next retraining scheduled at {next_run} (in {wait_seconds/3600:.2f} hours)")
        
        time.sleep(wait_seconds)
        run_retraining()

if __name__ == "__main__":
    main()
