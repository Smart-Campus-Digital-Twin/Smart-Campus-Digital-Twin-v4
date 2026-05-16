"""Shared SparkSession factory for all Spark batch jobs."""

from __future__ import annotations

from pyspark.sql import SparkSession

from processing.spark.config import config


def build_spark_session(job_name: str) -> SparkSession:
    """Return a fully-configured SparkSession for the given job name.

    Uses getOrCreate() so that tests can pre-configure a local session
    without this factory overriding it.
    """
    return (
        SparkSession.builder
        .appName(f"{config.spark_app_name}-{job_name}")
        .master(config.spark_master)
        .config("spark.executor.memory", config.spark_executor_mem)
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
