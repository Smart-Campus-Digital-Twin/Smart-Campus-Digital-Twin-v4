"""
Real-time metrics endpoints — all data served from InfluxDB.

These endpoints are designed for low-latency reads (< 200 ms P99).
All queries target pre-aggregated buckets (campus_1m, campus_1h) except
/live which queries campus_raw for the last few minutes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api.clients import InfluxAPIClient
from api.dependencies import get_influx
from api.schemas import AggregatedPeriod, LiveReading

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/live/{building_id}",
    response_model=list[LiveReading],
    summary="Latest reading per sensor in a building",
)
async def live(
    building_id:    str,
    range_minutes:  int   = Query(default=5, ge=1, le=60,
                                  description="Look-back window in minutes"),
    influx:         InfluxAPIClient = Depends(get_influx),
) -> list[LiveReading]:
    df = await influx.latest_readings(building_id, range_minutes)

    if df.empty:
        return []

    results = []
    for _, row in df.iterrows():
        try:
            sensor_id = row.get("sensor_id")
            if not sensor_id:
                continue
            results.append(LiveReading(
                sensor_id   = sensor_id,
                room_id     = row["room_id"],
                building_id = row["building_id"],
                floor       = int(row["floor"]),
                sensor_type = row["sensor_type"],
                value       = float(row["value"]),
                unit        = _unit_for(row["sensor_type"]),
                ts          = row["_time"],
                quality     = float(row.get("quality", 1.0)),
            ))
        except (KeyError, ValueError):
            continue  # skip malformed rows

    return results


@router.get(
    "/history/{room_id}",
    response_model=list[AggregatedPeriod],
    summary="Aggregated time-series history for a room",
)
async def history(
    room_id:     str,
    start:       datetime = Query(...,  description="Range start (ISO 8601)"),
    stop:        datetime | None = Query(
        default=None,
        description="Range end (ISO 8601). Defaults to now.",
    ),
    sensor_type: str | None = Query(default=None,
                                    description="Filter by sensor type: temperature | occupancy | energy"),
    resolution:  str        = Query(default="1h",
                                    pattern="^(1m|1h)$",
                                    description="Bucket resolution: 1m or 1h"),
    influx:      InfluxAPIClient = Depends(get_influx),
) -> list[AggregatedPeriod]:
    if stop is None:
        stop = datetime.now(UTC)
    if stop <= start:
        raise HTTPException(status_code=422, detail="stop must be after start")

    df = await influx.room_history(
        room_id     = room_id,
        start       = start,
        stop        = stop,
        sensor_type = sensor_type,
        resolution  = resolution,
    )

    if df.empty:
        return []

    results = []
    for _, row in df.iterrows():
        try:
            results.append(AggregatedPeriod(
                ts          = row["_time"],
                room_id     = row["room_id"],
                building_id = row["building_id"],
                sensor_type = row["sensor_type"],
                min         = float(row.get("min", 0)),
                max         = float(row.get("max", 0)),
                avg         = float(row.get("avg", 0)),
                stddev      = float(row.get("stddev", 0)),
                count       = int(row.get("count", 0)),
                quality_avg = float(row.get("quality_avg", 0.0)),
            ))
        except (KeyError, ValueError):
            continue

    return results


def _unit_for(sensor_type: str) -> str:
    return {"temperature": "celsius", "occupancy": "count", "energy": "watt"}.get(sensor_type, "")
