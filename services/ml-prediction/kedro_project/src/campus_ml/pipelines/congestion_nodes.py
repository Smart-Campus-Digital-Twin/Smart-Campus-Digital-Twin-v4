"""
Canteen & Library congestion pipelines.
Prediction target: avg occupancy for the *next* 30-min / 1-hour slot.
Model: XGBoost regressor tracked with MLflow.
"""
from __future__ import annotations

import json
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

# ── Feature columns used for training ────────────────────────────────────────

_BASE_FEATURES = [
    "sin_hour", "cos_hour", "sin_dow", "cos_dow", "sin_month", "cos_month",
    "is_weekend", "is_holiday",
    "is_exam_period", "is_low_attendance", "is_essentially_empty",
    "tua_active", "lecture_scale", "congestion_fraction",
    "has_event",
    "capacity",
]

_ACTIVITY_FEATURES = [
    "act_lecture_day", "act_exam_day", "act_low_attendance",
    "act_essentially_empty", "act_weekend", "act_holiday", "act_normal",
]


def _lag_feature_names(lags: list[int], windows: list[int]) -> list[str]:
    lag_cols = [f"lag_{n}" for n in lags]
    roll_cols = [f"roll_mean_{w}" for w in windows] + [f"roll_std_{w}" for w in windows]
    return lag_cols + roll_cols


# ── Nodes ─────────────────────────────────────────────────────────────────────

def build_congestion_features(
    raw: pd.DataFrame,
    congestion_lags: list[int],
    rolling_windows: list[int],
    group_col: str = "room_id",
) -> pd.DataFrame:
    """
    Feature engineering node shared by canteen and library.
    Adds temporal, lag, and categorical features.
    Target column (next-window avg) is created by shifting avg one step forward.
    """
    df = add_temporal_features(raw, ts_col="timestamp")
    df = encode_categoricals(df)

    # Sort so lags are computed correctly per entity
    df = df.sort_values([group_col, "timestamp"]).reset_index(drop=True)

    df = add_lag_features(df, target_col="avg", group_col=group_col,
                          lags=congestion_lags, rolling_windows=rolling_windows)

    # Target: next-slot avg (shift -1 within each group)
    df["target"] = df.groupby(group_col)["avg"].shift(-1)

    # Drop rows with no target (last row per entity) or no lag (warm-up rows)
    max_lag = max(congestion_lags)
    lag_cols = _lag_feature_names(congestion_lags, rolling_windows)
    df = df.dropna(subset=["target"] + lag_cols)

    log.info("Congestion features built: %d rows, %d columns", len(df), df.shape[1])
    return df


def split_congestion_data(
    features: pd.DataFrame,
    train_cutoff_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train, test = time_split(features, cutoff=train_cutoff_date, ts_col="timestamp")
    log.info("Train: %d rows | Test: %d rows", len(train), len(test))
    return train, test


def train_congestion_model(
    train: pd.DataFrame,
    test: pd.DataFrame,
    xgb_params: dict[str, Any],
    mlflow_tracking_uri: str,
    experiment_name: str,
    model_name: str,
    congestion_lags: list[int],
    rolling_windows: list[int],
) -> dict:
    """
    Train an XGBoost regressor, log to MLflow, register the model, and return
    a dict with the run_id and registered model version.
    """
    feature_cols = (
        _BASE_FEATURES + _ACTIVITY_FEATURES
        + _lag_feature_names(congestion_lags, rolling_windows)
    )
    # Filter to only columns that exist (handles optional features gracefully)
    feature_cols = [c for c in feature_cols if c in train.columns]

    X_train, y_train = train[feature_cols], train["target"]
    X_test,  y_test  = test[feature_cols],  test["target"]

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(experiment_name)

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
            registered_model_name=model_name,
        )

        run_id = run.info.run_id
        log.info("[%s] MAE=%.4f  RMSE=%.4f  run_id=%s", model_name, mae, rmse, run_id)

    return {"run_id": run_id, "model_name": model_name, "mae": mae, "rmse": rmse}
