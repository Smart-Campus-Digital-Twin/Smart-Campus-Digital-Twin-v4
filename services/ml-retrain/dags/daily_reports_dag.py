"""
Airflow DAG — daily_reports
=============================
Runs DailyEnergyReportJob at 00:30 for yesterday's data.

Reads InfluxDB campus_1h → writes PostgreSQL energy_daily.

The 30-minute offset gives the last hourly_rollup run (00:05) time to
complete before this DAG starts reading from campus_1h.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

from callbacks import on_task_failure

_DEFAULT_ARGS = {
    "owner":               "campus-platform",
    "depends_on_past":     False,
    "retries":             2,
    "retry_delay":         timedelta(minutes=10),
    "email_on_failure":    False,
    "on_failure_callback": on_task_failure,
    "sla":                 timedelta(hours=2),
}

with DAG(
    dag_id            = "daily_reports",
    description       = "Daily energy summary: InfluxDB campus_1h → PostgreSQL energy_daily",
    schedule_interval = "30 0 * * *",  # 00:30 daily
    start_date        = datetime(2025, 1, 1),
    catchup           = False,
    max_active_runs   = 1,
    default_args      = _DEFAULT_ARGS,
    tags              = ["postgres", "spark", "daily", "energy"],
) as dag:

    daily_energy = SparkSubmitOperator(
        task_id         = "daily_energy_report",
        application     = "/opt/campus/processing/spark/jobs/daily_energy_report.py",
        conn_id         = "spark_default",
        conf            = {
            "spark.driver.memory": "512m",
        },
        application_args = [
            "--date",
            "{{ data_interval_start.strftime('%Y-%m-%d') }}",
        ],
        packages        = "org.postgresql:postgresql:42.7.3",
        verbose         = False,
    )
