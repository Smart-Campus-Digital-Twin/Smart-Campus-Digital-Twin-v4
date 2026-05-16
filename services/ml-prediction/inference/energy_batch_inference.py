"""
Energy Batch Inference — runs daily via Airflow DAG.
Reads the latest energy_daily data from PostgreSQL, computes lag features,
loads the production XGBoost model from MLflow, generates next-hour predictions
for each building, and writes results back to ml_energy_features in PostgreSQL.
"""
from __future__ import annotations

import os
import logging
from datetime import date, timedelta, datetime

import mlflow
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Config from env ───────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
PG_HOST   = os.environ.get("POSTGRES_HOST", "postgres")
PG_PORT   = int(os.environ.get("POSTGRES_PORT", 5432))
PG_DB     = os.environ.get("POSTGRES_DB", "campus")
PG_USER   = os.environ.get("POSTGRES_USER", "campus")
PG_PASS   = os.environ.get("POSTGRES_PASSWORD", "campus")

MODEL_NAME  = "campus_energy_forecast"
MODEL_STAGE = "Production"

BUILDING_TYPE_MAP = {
    "academic": 0, "admin": 1, "canteen": 2, "hostel": 3,
    "library": 4, "lecture_hall": 5, "event_hall": 6, "outdoor_venue": 7,
}


def get_connection():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
    )


def load_recent_energy(conn, lookback_days: int = 30) -> pd.DataFrame:
    """Pull recent daily energy rows for lag feature computation."""
    cutoff = date.today() - timedelta(days=lookback_days)
    sql = """
        SELECT date, building_id, total_kwh AS total_energy_kwh,
               avg_w, peak_w
        FROM energy_daily
        WHERE date >= %s
        ORDER BY building_id, date
    """
    df = pd.read_sql(sql, conn, params=(cutoff,))
    df["date"] = pd.to_datetime(df["date"])
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the same feature vector as the training pipeline expects.
    For daily batch inference, lags are computed over days (1d, 7d, 14d).
    """
    df = df.sort_values(["building_id", "date"]).copy()
    g = df.groupby("building_id")["total_energy_kwh"]
    for lag in [1, 7, 14]:
        df[f"lag_{lag}"] = g.shift(lag)
    for w in [3, 7]:
        df[f"roll_mean_{w}"] = g.shift(1).rolling(w).mean().reset_index(level=0, drop=True)
        df[f"roll_std_{w}"]  = g.shift(1).rolling(w).std().reset_index(level=0, drop=True)

    df["dow"]   = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    import numpy as np
    df["sin_dow"],   df["cos_dow"]   = (
        np.sin(2*np.pi*df["dow"]/7),  np.cos(2*np.pi*df["dow"]/7))
    df["sin_month"], df["cos_month"] = (
        np.sin(2*np.pi*df["month"]/12), np.cos(2*np.pi*df["month"]/12))
    return df.dropna()


def write_predictions(conn, rows: list[tuple]) -> None:
    sql = """
        INSERT INTO ml_energy_features
            (date, building_id, total_energy_kwh, written_at)
        VALUES %s
        ON CONFLICT (date, building_id) DO UPDATE
            SET total_energy_kwh = EXCLUDED.total_energy_kwh,
                written_at = EXCLUDED.written_at
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()


def main():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    log.info("Loading model '%s' @ stage '%s'", MODEL_NAME, MODEL_STAGE)
    model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{MODEL_STAGE}")

    conn = get_connection()
    df = load_recent_energy(conn)
    df = compute_features(df)

    # Only predict for 'today' (latest available date per building)
    latest = df.groupby("building_id")["date"].max().reset_index()
    df_pred = df.merge(latest, on=["building_id", "date"])

    feature_cols = [c for c in df_pred.columns
                    if c not in ("date", "building_id", "total_energy_kwh", "avg_w", "peak_w")]
    predictions = model.predict(df_pred[feature_cols])

    target_date = date.today() + timedelta(days=1)
    now = datetime.utcnow()
    rows = [
        (target_date, row["building_id"], float(pred), now)
        for (_, row), pred in zip(df_pred.iterrows(), predictions)
    ]

    write_predictions(conn, rows)
    conn.close()
    log.info("Wrote %d predictions for %s", len(rows), target_date)


if __name__ == "__main__":
    main()
