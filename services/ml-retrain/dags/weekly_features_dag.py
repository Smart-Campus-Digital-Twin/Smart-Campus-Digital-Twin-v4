"""
Airflow DAG — weekly_ml_features
==================================
Runs WeeklyMLFeaturesJob every Monday at 02:00 for the previous week.

Reads InfluxDB campus_1h → joins PostgreSQL rooms → writes PostgreSQL ml_features.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

from callbacks import on_task_failure

_DEFAULT_ARGS = {
    "owner":               "campus-platform",
    "depends_on_past":     False,
    "retries":             1,
    "retry_delay":         timedelta(minutes=20),
    "email_on_failure":    False,
    "on_failure_callback": on_task_failure,
    "sla":                 timedelta(hours=4),
}

with DAG(
    dag_id            = "weekly_ml_features",
    description       = "Weekly ML feature store: InfluxDB campus_1h → PostgreSQL ml_features",
    schedule_interval = "0 2 * * 1",   # 02:00 every Monday
    start_date        = datetime(2025, 1, 6),  # first Monday
    catchup           = False,          # no historical backfill by default (run manually if needed)
    max_active_runs   = 1,
    default_args      = _DEFAULT_ARGS,
    tags              = ["postgres", "spark", "weekly", "ml"],
) as dag:

    weekly_features = SparkSubmitOperator(
        task_id         = "weekly_ml_features",
        application     = "/opt/campus/processing/spark/jobs/weekly_ml_features.py",
        conn_id         = "spark_default",
        conf            = {
            "spark.driver.memory": "1g",
        },
        application_args = [
            "--week-start",
            "{{ data_interval_start.strftime('%Y-%m-%d') }}",
        ],
        packages        = "org.postgresql:postgresql:42.7.3",
        verbose         = False,
    )
