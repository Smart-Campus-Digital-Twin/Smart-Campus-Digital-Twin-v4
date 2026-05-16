"""
Airflow DAG — hourly_rollup
============================
Runs HourlyRollupJob at hh:05 for the previous hour.

Reads InfluxDB campus_1m → writes InfluxDB campus_1h.
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
    "retry_delay":         timedelta(minutes=5),
    "email_on_failure":    False,
    "on_failure_callback": on_task_failure,
    "sla":                 timedelta(minutes=55),
}

with DAG(
    dag_id            = "hourly_rollup",
    description       = "Roll up 1-min aggregations → 1-hour in InfluxDB",
    schedule_interval = "5 * * * *",   # every hour at hh:05
    start_date        = datetime(2025, 1, 1),
    catchup           = False,
    max_active_runs   = 1,
    default_args      = _DEFAULT_ARGS,
    tags              = ["influxdb", "spark", "hourly"],
) as dag:

    hourly_rollup = SparkSubmitOperator(
        task_id         = "hourly_rollup",
        application     = "/opt/campus/processing/spark/jobs/hourly_rollup.py",
        conn_id         = "spark_default",
        conf            = {
            "spark.driver.memory": "512m",
        },
        application_args = [
            "--hour",
            "{{ data_interval_start.strftime('%Y-%m-%dT%H:00:00Z') }}",
        ],
        verbose         = False,
    )
