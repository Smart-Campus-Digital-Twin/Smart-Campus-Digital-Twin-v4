"""Shared Airflow task and DAG callbacks."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def on_task_failure(context: dict) -> None:
    """Log a structured failure record for every failed task.

    Airflow sets email_on_failure=False in our DAGs because we do not want
    email spam.  This callback provides a structured log line that can be
    ingested by the ELK stack and trigger PagerDuty/Slack via log-based alerts.
    """
    dag_id   = context.get("dag").dag_id if context.get("dag") else "unknown"
    task_id  = context.get("task_instance").task_id if context.get("task_instance") else "unknown"
    run_id   = context.get("run_id", "unknown")
    exc      = context.get("exception")

    logger.error(
        "Airflow task failed",
        extra={
            "dag_id":    dag_id,
            "task_id":   task_id,
            "run_id":    run_id,
            "exception": str(exc) if exc else None,
        },
    )
