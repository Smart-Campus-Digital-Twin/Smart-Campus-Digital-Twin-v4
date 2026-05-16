"""
Airflow DAG: ML Training
Runs the full Kedro ML pipelines (canteen, library, energy) on a schedule.
Training is NOT run on every data arrival — only on the defined schedule.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "smart_campus",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

KEDRO_CMD = (
    "docker exec campus-ml-training "
    "bash -c 'cd /opt/campus/ml/kedro_project && "
    "MLFLOW_TRACKING_URI=http://mlflow:5000 "
    "python -W ignore -m kedro run --pipeline {pipeline}'"
)

with DAG(
    dag_id="ml_training",
    description="Daily Kedro ML model training for congestion and energy models",
    schedule_interval="0 2 * * *",   # Every day at 02:00 campus time
    start_date=datetime(2025, 1, 6, tzinfo=None),
    catchup=False,
    default_args=default_args,
    tags=["ml", "training"],
) as dag:

    train_canteen = BashOperator(
        task_id="train_canteen_congestion",
        bash_command=KEDRO_CMD.format(pipeline="canteen_congestion"),
    )

    train_library = BashOperator(
        task_id="train_library_congestion",
        bash_command=KEDRO_CMD.format(pipeline="library_congestion"),
    )

    train_energy = BashOperator(
        task_id="train_energy_forecast",
        bash_command=KEDRO_CMD.format(pipeline="energy_forecast"),
    )

    # Canteen and library can run in parallel; energy after both (same features)
    [train_canteen, train_library] >> train_energy
