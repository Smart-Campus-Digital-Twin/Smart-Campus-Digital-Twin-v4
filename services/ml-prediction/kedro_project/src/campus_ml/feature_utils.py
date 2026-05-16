"""
Feature engineering shared utilities.
All three domains (canteen, library, energy) call these helpers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Cyclical encoding
# ---------------------------------------------------------------------------

def _sin_cos(series: pd.Series, period: float) -> tuple[pd.Series, pd.Series]:
    rad = 2 * np.pi * series / period
    return np.sin(rad), np.cos(rad)


def add_temporal_features(df: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    """Add sine/cosine cyclical time features derived from a UTC/TZ-aware timestamp."""
    df = df.copy()
    ts = pd.to_datetime(df[ts_col])
    df["hour"]       = ts.dt.hour + ts.dt.minute / 60.0
    df["dow"]        = ts.dt.dayofweek          # 0 = Monday
    df["month"]      = ts.dt.month
    df["sin_hour"],  df["cos_hour"]  = _sin_cos(df["hour"],  24.0)
    df["sin_dow"],   df["cos_dow"]   = _sin_cos(df["dow"],    7.0)
    df["sin_month"], df["cos_month"] = _sin_cos(df["month"], 12.0)
    return df


# ---------------------------------------------------------------------------
# Lag and rolling features
# ---------------------------------------------------------------------------

def add_lag_features(
    df: pd.DataFrame,
    target_col: str,
    group_col: str,
    lags: list[int],
    rolling_windows: list[int],
) -> pd.DataFrame:
    """
    For each entity (room_id or building_id) create:
      - lag_{n}   : target shifted n steps back
      - roll_mean_{w}, roll_std_{w} : rolling stats over w steps
    df MUST already be sorted by (group_col, timestamp) ascending.
    """
    df = df.copy()
    grouped = df.groupby(group_col)[target_col]

    for lag in lags:
        df[f"lag_{lag}"] = grouped.shift(lag)

    for w in rolling_windows:
        roll = grouped.shift(1).rolling(w)
        df[f"roll_mean_{w}"] = roll.mean().reset_index(level=0, drop=True)
        df[f"roll_std_{w}"]  = roll.std().reset_index(level=0, drop=True)

    return df


# ---------------------------------------------------------------------------
# Categorical encoding
# ---------------------------------------------------------------------------

ACTIVITY_TYPES = [
    "lecture_day", "exam_day", "low_attendance", "essentially_empty",
    "weekend", "holiday", "normal",
]


def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot encode activity_type; encode active_events as multi-hot flags."""
    df = df.copy()

    # activity_type → one-hot
    for at in ACTIVITY_TYPES:
        df[f"act_{at}"] = (df["activity_type"] == at).astype("int8")

    # active_events → multi-hot: flag any non-empty event
    df["has_event"] = (df["active_events"].fillna("").str.len() > 0).astype("int8")

    return df


# ---------------------------------------------------------------------------
# Train/test split (time-aware, no shuffle)
# ---------------------------------------------------------------------------

def time_split(
    df: pd.DataFrame,
    cutoff: str,
    ts_col: str = "timestamp",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split df at the cutoff date. Train < cutoff, test >= cutoff."""
    mask = pd.to_datetime(df[ts_col]) < pd.Timestamp(cutoff, tz="UTC")
    return df[mask].copy(), df[~mask].copy()
