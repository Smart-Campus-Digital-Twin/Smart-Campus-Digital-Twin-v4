"""
Kedro pipeline definitions for all three ML domains:
  1. canteen_congestion
  2. library_congestion
  3. energy_forecast
"""
from __future__ import annotations

from kedro.pipeline import Pipeline, node, pipeline

from campus_ml.pipelines.congestion_nodes import (
    build_congestion_features,
    split_congestion_data,
    train_congestion_model,
)
from campus_ml.pipelines.energy_nodes import (
    build_energy_features,
    split_energy_data,
    train_energy_model,
)


# ── Canteen pipeline ──────────────────────────────────────────────────────────

def create_canteen_pipeline() -> Pipeline:
    return pipeline([
        node(
            func=lambda raw, lags, windows: build_congestion_features(raw, lags, windows, group_col="room_id"),
            inputs=["canteen_raw", "params:congestion_lags", "params:rolling_windows"],
            outputs="canteen_features",
            name="canteen_feature_engineering",
        ),
        node(
            func=split_congestion_data,
            inputs=["canteen_features", "params:train_cutoff_date"],
            outputs=["canteen_train", "canteen_test"],
            name="canteen_split",
        ),
        node(
            func=lambda train, test, xgb, uri, lags, windows: train_congestion_model(
                train, test, xgb, uri,
                experiment_name="campus_canteen_congestion",
                model_name="campus_canteen_congestion",
                congestion_lags=lags,
                rolling_windows=windows,
            ),
            inputs=[
                "canteen_train", "canteen_test",
                "params:xgb_params",
                "params:mlflow_tracking_uri",
                "params:congestion_lags",
                "params:rolling_windows",
            ],
            outputs="canteen_model_info",
            name="canteen_train_model",
        ),
    ])


# ── Library pipeline ──────────────────────────────────────────────────────────

def create_library_pipeline() -> Pipeline:
    return pipeline([
        node(
            func=lambda raw, lags, windows: build_congestion_features(raw, lags, windows, group_col="room_id"),
            inputs=["library_raw", "params:congestion_lags", "params:rolling_windows"],
            outputs="library_features",
            name="library_feature_engineering",
        ),
        node(
            func=split_congestion_data,
            inputs=["library_features", "params:train_cutoff_date"],
            outputs=["library_train", "library_test"],
            name="library_split",
        ),
        node(
            func=lambda train, test, xgb, uri, lags, windows: train_congestion_model(
                train, test, xgb, uri,
                experiment_name="campus_library_congestion",
                model_name="campus_library_congestion",
                congestion_lags=lags,
                rolling_windows=windows,
            ),
            inputs=[
                "library_train", "library_test",
                "params:xgb_params",
                "params:mlflow_tracking_uri",
                "params:congestion_lags",
                "params:rolling_windows",
            ],
            outputs="library_model_info",
            name="library_train_model",
        ),
    ])


# ── Energy pipeline ───────────────────────────────────────────────────────────

def create_energy_pipeline() -> Pipeline:
    return pipeline([
        node(
            func=build_energy_features,
            inputs=["energy_raw", "params:energy_lags", "params:rolling_windows"],
            outputs="energy_features",
            name="energy_feature_engineering",
        ),
        node(
            func=split_energy_data,
            inputs=["energy_features", "params:train_cutoff_date"],
            outputs=["energy_train", "energy_test"],
            name="energy_split",
        ),
        node(
            func=train_energy_model,
            inputs=[
                "energy_train", "energy_test",
                "params:xgb_params",
                "params:mlflow_tracking_uri",
                "params:mlflow_experiment_energy",
                "params:energy_lags",
                "params:rolling_windows",
            ],
            outputs="energy_model_info",
            name="energy_train_model",
        ),
    ])
