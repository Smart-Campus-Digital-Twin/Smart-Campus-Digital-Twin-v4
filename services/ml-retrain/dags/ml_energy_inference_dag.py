"""
Airflow DAG: Daily Energy Batch Inference
Runs every day after the nightly Spark daily energy rollup.
Loads the latest registered MLflow energy model and writes next-day
hourly energy predictions to the ml_energy_features PostgreSQL table.
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

INFERENCE_CMD = (
    "docker exec campus-ml-inference "
    "bash -c 'MLFLOW_TRACKING_URI=http://mlflow:5000 "
    "python /opt/campus/ml/inference/energy_batch_inference.py'"
)

with DAG(
    dag_id="ml_energy_batch_inference",
    description="Daily batch inference: predict next-day hourly energy per building",
    schedule_interval="30 1 * * *",   # 01:30 campus time — after Spark daily rollup
    start_date=datetime(2025, 1, 2, tzinfo=None),
    catchup=False,
    default_args=default_args,
    tags=["ml", "inference", "energy"],
) as dag:

    run_inference = BashOperator(
        task_id="energy_batch_inference",
        bash_command=INFERENCE_CMD,
    )
