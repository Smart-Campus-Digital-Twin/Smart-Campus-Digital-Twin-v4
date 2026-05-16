"""
ML Prediction Service - Lightweight FastAPI microservice for real-time predictions.

This service:
- Loads XGBoost models from MLflow at startup (not per request)
- Exposes REST API for congestion and energy predictions
- Writes predictions to InfluxDB
- Handles feature engineering for incoming sensor data
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

try:
    import mlflow
    import mlflow.pyfunc
except Exception as exc:  # noqa: BLE001
    mlflow = None  # type: ignore[assignment]
    log.warning("MLflow import disabled: %s", exc)

# ── Config ────────────────────────────────────────────────────────────────────
INFLUX_URL = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUX_ORG = os.environ.get("INFLUXDB_ORG", "smart-campus")
INFLUX_BUCKET = os.environ.get("INFLUXDB_BUCKET", "campus_predictions")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")

CANTEEN_MODEL_NAME = "campus_canteen_congestion"
LIBRARY_MODEL_NAME = "campus_library_congestion"
ENERGY_MODEL_NAME = "campus_energy_forecast"

LAGS_NEEDED = [1, 2, 4, 8, 48]

# ── Global state ──────────────────────────────────────────────────────────────
models: dict[str, XGBRegressor] = {}
influx_client: InfluxDBClient | None = None
write_api = None


# ── Pydantic Models ───────────────────────────────────────────────────────────
class CongestionPredictionRequest(BaseModel):
    room_id: str
    room_type: str = Field(..., pattern="^(canteen|library)$")
    building_id: str
    timestamp: str
    avg: float = Field(..., ge=0)
    capacity: float = Field(default=100, ge=1)
    history: list[float] = Field(default_factory=list, max_length=50)
    context: dict[str, Any] = Field(default_factory=dict)


class PredictionResponse(BaseModel):
    room_id: str
    predicted_avg: float
    actual_avg: float
    timestamp: str
    written_to_influx: bool


# ── Lifespan context manager ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models at startup, close connections at shutdown."""
    global models, influx_client, write_api

    log.info("Starting ML Prediction Service...")

    # Initialize InfluxDB client
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    log.info("InfluxDB client initialized")

    # Load models from MLflow if the dependency is available.
    if mlflow is None:
        log.warning("MLflow is unavailable; prediction models will not be loaded.")
    else:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()

        for model_name, model_key in [
            (CANTEEN_MODEL_NAME, "canteen"),
            (LIBRARY_MODEL_NAME, "library"),
            (ENERGY_MODEL_NAME, "energy"),
        ]:
            try:
                versions = client.get_latest_versions(model_name, stages=["Production"])
                if not versions:
                    log.warning("No Production version for '%s' — skipping.", model_name)
                    continue
                run_id = versions[0].run_id
                model_uri = f"models:/{model_name}/Production"
                models[model_key] = mlflow.pyfunc.load_model(model_uri)
                log.info("Loaded model '%s' (run=%s)", model_name, run_id[:8])
            except Exception as exc:
                log.warning("Failed to load model '%s': %s", model_name, exc)

    log.info("Loaded %d models: %s", len(models), list(models.keys()))

    yield

    # Cleanup
    if influx_client:
        influx_client.close()
    log.info("ML Prediction Service shutdown complete")


app = FastAPI(
    title="Smart Campus ML Prediction Service",
    description="Lightweight prediction API for congestion and energy forecasting",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Feature Engineering ───────────────────────────────────────────────────────
def build_congestion_features(req: CongestionPredictionRequest) -> np.ndarray | None:
    """Build feature vector for congestion prediction."""
    history = req.history
    if len(history) < max(LAGS_NEEDED):
        return None

    ts = datetime.fromisoformat(req.timestamp)
    hour = ts.hour + ts.minute / 60.0
    dow = ts.weekday()
    month = ts.month

    sin_h, cos_h = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    sin_d, cos_d = np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)
    sin_m, cos_m = np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)

    lags = [history[-n] if n <= len(history) else 0.0 for n in LAGS_NEEDED]
    roll3 = float(np.mean(history[-3:])) if len(history) >= 3 else 0.0
    roll6 = float(np.mean(history[-6:])) if len(history) >= 6 else 0.0
    std3 = float(np.std(history[-3:])) if len(history) >= 3 else 0.0
    std6 = float(np.std(history[-6:])) if len(history) >= 6 else 0.0

    ctx = req.context
    feat = [
        sin_h, cos_h, sin_d, cos_d, sin_m, cos_m,
        float(ctx.get("is_weekend", 0)),
        float(ctx.get("is_holiday", 0)),
        float(ctx.get("is_exam_period", 0)),
        float(ctx.get("is_low_attendance", 0)),
        float(ctx.get("is_essentially_empty", 0)),
        float(ctx.get("tua_active", 0)),
        float(ctx.get("lecture_scale", 1.0)),
        float(ctx.get("congestion_fraction", 1.0)),
        float(1 if ctx.get("active_events") else 0),
        float(req.capacity),
        # activity one-hots — zeros for now
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        *lags,
        roll3, roll6, std3, std6,
    ]
    return np.array(feat, dtype=np.float32).reshape(1, -1)


# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "models_loaded": list(models.keys()),
        "influx_connected": influx_client is not None,
    }


@app.post("/predict/congestion", response_model=PredictionResponse)
async def predict_congestion(req: CongestionPredictionRequest):
    """
    Predict next-slot occupancy for canteen or library.
    Writes prediction to InfluxDB and returns the result.
    """
    model = models.get(req.room_type)
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"Model for room_type '{req.room_type}' not available",
        )

    features = build_congestion_features(req)
    if features is None:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient history: need {max(LAGS_NEEDED)} values, got {len(req.history)}",
        )

    try:
        df = pd.DataFrame(features)
        prediction = float(model.predict(df)[0])
    except Exception as exc:
        log.error("Prediction failed for room %s: %s", req.room_id, exc)
        raise HTTPException(status_code=500, detail=f"Prediction error: {exc}")

    # Write to InfluxDB
    written = False
    if write_api:
        try:
            point = (
                Point("predicted_occupancy")
                .tag("room_id", req.room_id)
                .tag("building_id", req.building_id)
                .tag("room_type", req.room_type)
                .field("predicted_avg", prediction)
                .field("actual_avg", req.avg)
                .time(req.timestamp, WritePrecision.S)
            )
            write_api.write(bucket=INFLUX_BUCKET, record=point)
            written = True
        except Exception as exc:
            log.warning("InfluxDB write failed: %s", exc)

    return PredictionResponse(
        room_id=req.room_id,
        predicted_avg=prediction,
        actual_avg=req.avg,
        timestamp=req.timestamp,
        written_to_influx=written,
    )


@app.get("/models")
async def list_models():
    """List loaded models and their metadata."""
    return {
        "models": {
            key: {
                "loaded": True,
                "type": "XGBRegressor",
            }
            for key in models.keys()
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info",
    )
