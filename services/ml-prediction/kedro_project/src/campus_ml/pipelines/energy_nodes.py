"""
Energy forecast pipeline nodes.
Target: total_energy_kwh for the *next hour* per building.
Model:  XGBoost regressor tracked with MLflow.
For daily summary, the Airflow DAG aggregates hourly predictions.
"""
from __future__ import annotations

import logging
from typing import Any

import mlflow
import mlflow.xgboost
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from campus_ml.feature_utils import (
    add_temporal_features,
    add_lag_features,
    encode_categoricals,
    time_split,
)

log = logging.getLogger(__name__)

_BASE_FEATURES = [
    "sin_hour", "cos_hour", "sin_dow", "cos_dow", "sin_month", "cos_month",
    "is_weekend", "is_holiday",
    "is_exam_period", "is_low_attendance", "is_essentially_empty",
    "tua_active", "lecture_scale", "congestion_fraction",
    "has_event",
    "n_rooms", "total_capacity", "avg_occupancy_ratio",
]

_ACTIVITY_FEATURES = [
    "act_lecture_day", "act_exam_day", "act_low_attendance",
    "act_essentially_empty", "act_weekend", "act_holiday", "act_normal",
]

_BUILDING_TYPE_MAP = {
    "academic": 0, "admin": 1, "canteen": 2, "hostel": 3,
    "library": 4, "lecture_hall": 5, "event_hall": 6, "outdoor_venue": 7,
}


def _lag_feature_names(lags: list[int], windows: list[int]) -> list[str]:
    lag_cols = [f"lag_{n}" for n in lags]
    roll_cols = [f"roll_mean_{w}" for w in windows] + [f"roll_std_{w}" for w in windows]
    return lag_cols + roll_cols


def build_energy_features(
    raw: pd.DataFrame,
    energy_lags: list[int],
    rolling_windows: list[int],
) -> pd.DataFrame:
    """
    Feature engineering for energy forecasting.
    - Encodes building_type as ordinal integer.
    - Adds temporal, event, lag, and rolling features.
    - Target: next-hour total_energy_kwh per building.
    """
    df = add_temporal_features(raw, ts_col="timestamp")
    df = encode_categoricals(df)

    # Building type → integer
    df["building_type_enc"] = (
        df["building_type"].map(_BUILDING_TYPE_MAP).fillna(99).astype(int)
    )

    df = df.sort_values(["building_id", "timestamp"]).reset_index(drop=True)

    df = add_lag_features(
        df,
        target_col="total_energy_kwh",
        group_col="building_id",
        lags=energy_lags,
        rolling_windows=rolling_windows,
    )

    # Target: next-hour energy
    df["target"] = df.groupby("building_id")["total_energy_kwh"].shift(-1)

    lag_cols = _lag_feature_names(energy_lags, rolling_windows)
    df = df.dropna(subset=["target"] + lag_cols)

    log.info("Energy features built: %d rows, %d columns", len(df), df.shape[1])
    return df


def split_energy_data(
    features: pd.DataFrame,
    train_cutoff_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train, test = time_split(features, cutoff=train_cutoff_date, ts_col="timestamp")
    log.info("Energy train: %d rows | test: %d rows", len(train), len(test))
    return train, test


def train_energy_model(
    train: pd.DataFrame,
    test: pd.DataFrame,
    xgb_params: dict[str, Any],
    mlflow_tracking_uri: str,
    mlflow_experiment_energy: str,
    energy_lags: list[int],
    rolling_windows: list[int],
) -> dict:
    """
    Train XGBoost energy forecast model, log to MLflow and register it.
    """
    feature_cols = (
        _BASE_FEATURES + _ACTIVITY_FEATURES
        + ["building_type_enc"]
        + _lag_feature_names(energy_lags, rolling_windows)
    )
    feature_cols = [c for c in feature_cols if c in train.columns]

    X_train, y_train = train[feature_cols], train["target"]
    X_test,  y_test  = test[feature_cols],  test["target"]

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(mlflow_experiment_energy)

    with mlflow.start_run() as run:
        model = XGBRegressor(**xgb_params)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        preds = model.predict(X_test)
        mae   = mean_absolute_error(y_test, preds)
        rmse  = mean_squared_error(y_test, preds, squared=False)

        mlflow.log_params(xgb_params)
        mlflow.log_metric("mae",  mae)
        mlflow.log_metric("rmse", rmse)
        mlflow.log_param("feature_cols", ",".join(feature_cols))

        mlflow.xgboost.log_model(
            model,
            artifact_path="model",
            registered_model_name="campus_energy_forecast",
        )

        run_id = run.info.run_id
        log.info("[energy] MAE=%.4f  RMSE=%.4f  run_id=%s", mae, rmse, run_id)

    return {
        "run_id": run_id,
        "model_name": "campus_energy_forecast",
        "mae": mae,
        "rmse": rmse,
    }
