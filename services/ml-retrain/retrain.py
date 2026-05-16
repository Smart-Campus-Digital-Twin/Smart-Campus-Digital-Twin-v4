"""
Smart Campus retraining entrypoint.

Trains three XGBoost models matching the names the prediction service loads:
    - campus_canteen_congestion
    - campus_library_congestion
    - campus_energy_forecast

Data source preference: InfluxDB (last 90 days), CSV fallback at /app/datasets.
Feature engineering matches services/ml-prediction/prediction_service/main.py:build_congestion_features.

Run-to-completion. No CLI flags.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

log = logging.getLogger("retrain")

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
INFLUX_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUX_ORG = os.environ.get("INFLUXDB_ORG", "smart-campus")
INFLUX_BUCKET_SENSORS = os.environ.get("INFLUXDB_BUCKET_SENSORS", "campus_sensors")

DATASETS_DIR = Path(os.environ.get("DATASETS_DIR", "/app/datasets"))
TRAIN_DAYS = int(os.environ.get("TRAIN_DAYS", "90"))
TRAIN_TEST_SPLIT = 0.8

LAGS_NEEDED = [1, 2, 4, 8, 48]
ROLLING_WINDOWS = [3, 6]

CANTEEN_MODEL = "campus_canteen_congestion"
LIBRARY_MODEL = "campus_library_congestion"
ENERGY_MODEL = "campus_energy_forecast"

XGB_PARAMS = {
    "n_estimators": 400,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
}

ACTIVITY_TYPES = [
    "lecture_day", "exam_day", "low_attendance", "essentially_empty",
    "weekend", "holiday", "normal",
]


def _temporal(df: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    df = df.copy()
    ts = pd.to_datetime(df[ts_col], utc=True)
    df["hour"] = ts.dt.hour + ts.dt.minute / 60.0
    df["dow"] = ts.dt.dayofweek
    df["month"] = ts.dt.month
    df["sin_hour"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["cos_hour"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    df["sin_dow"] = np.sin(2 * np.pi * df["dow"] / 7.0)
    df["cos_dow"] = np.cos(2 * np.pi * df["dow"] / 7.0)
    df["sin_month"] = np.sin(2 * np.pi * df["month"] / 12.0)
    df["cos_month"] = np.cos(2 * np.pi * df["month"] / 12.0)
    return df


def _categoricals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    activity = df["activity_type"] if "activity_type" in df.columns else pd.Series([""] * len(df))
    for at in ACTIVITY_TYPES:
        df[f"act_{at}"] = (activity == at).astype("int8")
    events = df["active_events"] if "active_events" in df.columns else pd.Series([""] * len(df))
    df["has_event"] = (events.fillna("").astype(str).str.len() > 0).astype("int8")
    return df


def _add_lags(df: pd.DataFrame, target_col: str, group_col: str) -> pd.DataFrame:
    df = df.copy()
    grouped = df.groupby(group_col)[target_col]
    for lag in LAGS_NEEDED:
        df[f"lag_{lag}"] = grouped.shift(lag)
    for w in ROLLING_WINDOWS:
        roll = grouped.shift(1).rolling(w)
        df[f"roll_mean_{w}"] = roll.mean().reset_index(level=0, drop=True)
        df[f"roll_std_{w}"] = roll.std().reset_index(level=0, drop=True)
    return df


def _ensure_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    defaults = {
        "is_weekend": 0, "is_holiday": 0, "is_exam_period": 0,
        "is_low_attendance": 0, "is_essentially_empty": 0,
        "tua_active": 0, "lecture_scale": 1.0, "congestion_fraction": 1.0,
        "capacity": 100.0,
    }
    for k, v in defaults.items():
        if k not in df.columns:
            df[k] = v
    return df


CONGESTION_FEATURES = [
    "sin_hour", "cos_hour", "sin_dow", "cos_dow", "sin_month", "cos_month",
    "is_weekend", "is_holiday",
    "is_exam_period", "is_low_attendance", "is_essentially_empty",
    "tua_active", "lecture_scale", "congestion_fraction",
    "has_event",
    "capacity",
    "act_lecture_day", "act_exam_day", "act_low_attendance",
    "act_essentially_empty", "act_weekend", "act_holiday", "act_normal",
] + [f"lag_{n}" for n in LAGS_NEEDED] + [f"roll_mean_{w}" for w in ROLLING_WINDOWS] + [f"roll_std_{w}" for w in ROLLING_WINDOWS]


def _build_congestion_dataset(raw: pd.DataFrame, group_col: str = "room_id") -> pd.DataFrame:
    df = _temporal(raw)
    df = _categoricals(df)
    df = _ensure_context_flags(df)
    df = df.sort_values([group_col, "timestamp"]).reset_index(drop=True)
    df = _add_lags(df, target_col="avg", group_col=group_col)
    df["target"] = df.groupby(group_col)["avg"].shift(-1)
    lag_cols = [c for c in df.columns if c.startswith("lag_") or c.startswith("roll_")]
    df = df.dropna(subset=["target"] + lag_cols)
    return df


def _build_energy_dataset(raw: pd.DataFrame) -> pd.DataFrame:
    df = _temporal(raw)
    df = _categoricals(df)
    df = _ensure_context_flags(df)
    df = df.sort_values(["building_id", "timestamp"]).reset_index(drop=True)
    df = _add_lags(df, target_col="total_energy_kwh", group_col="building_id")
    df["target"] = df.groupby("building_id")["total_energy_kwh"].shift(-1)
    lag_cols = [c for c in df.columns if c.startswith("lag_") or c.startswith("roll_")]
    df = df.dropna(subset=["target"] + lag_cols)
    return df


def _load_csv(name: str) -> pd.DataFrame | None:
    path = DATASETS_DIR / name
    if not path.exists():
        log.warning("CSV fallback missing: %s", path)
        return None
    df = pd.read_csv(path)
    log.info("Loaded %d rows from %s", len(df), path)
    return df


def _load_influx_congestion(room_type: str) -> pd.DataFrame | None:
    if not INFLUX_TOKEN:
        return None
    try:
        from influxdb_client import InfluxDBClient
    except ImportError:
        return None
    flux = f'''
        from(bucket: "{INFLUX_BUCKET_SENSORS}")
            |> range(start: -{TRAIN_DAYS}d)
            |> filter(fn: (r) => r["_measurement"] == "occupancy_1h")
            |> filter(fn: (r) => r["room_type"] == "{room_type}")
            |> filter(fn: (r) => r["_field"] == "avg" or r["_field"] == "capacity")
            |> pivot(rowKey: ["_time", "room_id", "building_id"], columnKey: ["_field"], valueColumn: "_value")
    '''
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
            tables = client.query_api().query_data_frame(flux)
        if isinstance(tables, list):
            df = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
        else:
            df = tables
        if df is None or df.empty:
            return None
        df = df.rename(columns={"_time": "timestamp"})
        log.info("Loaded %d rows of %s congestion from Influx", len(df), room_type)
        return df
    except Exception as exc:
        log.warning("Influx query for %s failed: %s", room_type, exc)
        return None


def _load_influx_energy() -> pd.DataFrame | None:
    if not INFLUX_TOKEN:
        return None
    try:
        from influxdb_client import InfluxDBClient
    except ImportError:
        return None
    flux = f'''
        from(bucket: "{INFLUX_BUCKET_SENSORS}")
            |> range(start: -{TRAIN_DAYS}d)
            |> filter(fn: (r) => r["_measurement"] == "energy_1h")
            |> filter(fn: (r) => r["_field"] == "total_energy_kwh")
            |> pivot(rowKey: ["_time", "building_id"], columnKey: ["_field"], valueColumn: "_value")
    '''
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
            tables = client.query_api().query_data_frame(flux)
        if isinstance(tables, list):
            df = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
        else:
            df = tables
        if df is None or df.empty:
            return None
        df = df.rename(columns={"_time": "timestamp"})
        log.info("Loaded %d rows of energy from Influx", len(df))
        return df
    except Exception as exc:
        log.warning("Influx energy query failed: %s", exc)
        return None


def _time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values("timestamp").reset_index(drop=True)
    cutoff = int(len(df) * TRAIN_TEST_SPLIT)
    return df.iloc[:cutoff].copy(), df.iloc[cutoff:].copy()


def _train_and_register(
    df: pd.DataFrame,
    feature_cols: list[str],
    model_name: str,
    experiment_name: str,
) -> dict:
    feature_cols = [c for c in feature_cols if c in df.columns]
    train, test = _time_split(df)
    if len(train) < 50 or len(test) < 10:
        raise ValueError(f"Not enough data for {model_name}: train={len(train)} test={len(test)}")

    X_train, y_train = train[feature_cols], train["target"]
    X_test, y_test = test[feature_cols], test["target"]

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run() as run:
        model = XGBRegressor(**XGB_PARAMS)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
        preds = model.predict(X_test)
        mae = float(mean_absolute_error(y_test, preds))
        rmse = float(mean_squared_error(y_test, preds, squared=False))
        mlflow.log_params(XGB_PARAMS)
        mlflow.log_metric("mae", mae)
        mlflow.log_metric("rmse", rmse)
        mlflow.log_param("feature_cols", ",".join(feature_cols))
        mlflow.log_param("n_train", len(train))
        mlflow.log_param("n_test", len(test))
        mlflow.xgboost.log_model(model, artifact_path="model", registered_model_name=model_name)
        run_id = run.info.run_id

    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    versions = client.get_latest_versions(model_name)
    if versions:
        latest = max(versions, key=lambda v: int(v.version))
        client.transition_model_version_stage(
            name=model_name,
            version=latest.version,
            stage="Production",
            archive_existing_versions=True,
        )
        log.info("Promoted %s v%s to Production (mae=%.4f rmse=%.4f)", model_name, latest.version, mae, rmse)
    return {"run_id": run_id, "model": model_name, "mae": mae, "rmse": rmse}


def _train_congestion(room_type: str, model_name: str, csv_name: str) -> dict:
    raw = _load_influx_congestion(room_type)
    if raw is None or raw.empty:
        log.info("Falling back to CSV for %s", model_name)
        raw = _load_csv(csv_name)
    if raw is None or raw.empty:
        raise RuntimeError(f"No data available for {model_name}")
    df = _build_congestion_dataset(raw)
    return _train_and_register(df, CONGESTION_FEATURES, model_name, experiment_name=model_name)


def _train_energy() -> dict:
    raw = _load_influx_energy()
    if raw is None or raw.empty:
        log.info("Falling back to CSV for energy")
        raw = _load_csv("energy_forecast_2024_2025.csv")
    if raw is None or raw.empty:
        raise RuntimeError("No data available for energy")
    df = _build_energy_dataset(raw)
    energy_features = [c for c in CONGESTION_FEATURES if c != "capacity"]
    return _train_and_register(df, energy_features, ENERGY_MODEL, experiment_name=ENERGY_MODEL)


def train_all() -> None:
    log.info("=== Retraining all models (tracking=%s) ===", MLFLOW_TRACKING_URI)
    results = []
    results.append(_train_congestion("canteen", CANTEEN_MODEL, "canteen_congestion_2024_2025.csv"))
    results.append(_train_congestion("library", LIBRARY_MODEL, "library_congestion_2024_2025.csv"))
    results.append(_train_energy())
    for r in results:
        log.info("  done: %s mae=%.4f rmse=%.4f run=%s", r["model"], r["mae"], r["rmse"], r["run_id"][:8])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    train_all()
