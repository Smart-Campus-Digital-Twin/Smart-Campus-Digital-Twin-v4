"""
Predictions API Router - Proxy to ML Prediction Service

Provides endpoints for:
- Real-time congestion predictions
- Energy forecasts
- Model health status
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])

# ML Prediction Service URL
PREDICTION_SERVICE_URL = "http://ml-prediction:8001"


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


class ModelInfo(BaseModel):
    models: dict[str, dict[str, Any]]


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/health")
async def prediction_service_health():
    """Check if ML prediction service is healthy."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{PREDICTION_SERVICE_URL}/health")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        log.error("Prediction service health check failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Prediction service unavailable: {exc}",
        ) from exc


@router.post("/congestion", response_model=PredictionResponse)
async def predict_congestion(req: CongestionPredictionRequest):
    """
    Predict next-slot occupancy for a room (canteen or library).
    Forwards request to ML prediction service which writes to InfluxDB.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{PREDICTION_SERVICE_URL}/predict/congestion",
                json=req.model_dump(),
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        log.error("Prediction service returned error: %s", exc.response.text)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.json().get("detail", "Prediction failed"),
        ) from exc
    except Exception as exc:
        log.error("Failed to call prediction service: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Prediction service error: {exc}",
        ) from exc


@router.get("/models", response_model=ModelInfo)
async def list_models():
    """List all loaded models in the prediction service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{PREDICTION_SERVICE_URL}/models")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        log.error("Failed to fetch models: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Could not fetch models: {exc}",
        ) from exc
