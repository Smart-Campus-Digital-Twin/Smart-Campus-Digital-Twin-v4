"""
Flink Real-Time Congestion Prediction Job.

Reads sensor occupancy messages from Kafka (sensors.occupancy),
builds lag/rolling features from an in-process rolling history per room,
and calls the ML Prediction Service API for predictions.

Design notes:
  - parallelism=1 so a single Python operator owns all room histories —
    avoids splitting history across slots.
  - History is kept in a plain Python dict (self._history), NOT in Flink
    managed ListState, which would trigger expensive RocksDB I/O.
  - Predictions are delegated to a dedicated microservice that loads
    models once at startup, avoiding memory overhead in Flink workers.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.functions import KeyedProcessFunction, RuntimeContext
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream.connectors.kafka import (
    KafkaSource, KafkaOffsetsInitializer,
)
from pyflink.common.serialization import SimpleStringSchema

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_BROKERS          = os.environ.get("KAFKA_BROKERS",         "kafka:9092")
PREDICTION_SERVICE_URL = os.environ.get("PREDICTION_SERVICE_URL", "http://ml-prediction:8001")

HISTORY_SLOTS = 50    # ~25 hours of 30-min windows per room
LAGS_NEEDED   = [1, 2, 4, 8, 48]

# Mapping building_id → room_type for congestion prediction targets.
# Only these buildings are predicted; all other occupancy readings are skipped.
_CANTEEN_BUILDINGS = {"goda-canteen", "sentra-court", "l-canteen", "wala-canteen"}
_LIBRARY_BUILDINGS = {"library"}


def _infer_room_type(building_id: str) -> str | None:
    """Return 'canteen', 'library', or None if this building is not a prediction target."""
    if building_id in _CANTEEN_BUILDINGS:
        return "canteen"
    if building_id in _LIBRARY_BUILDINGS:
        return "library"
    return None




# ── Flink Process Function ────────────────────────────────────────────────────

class CongestionPredictionFunction(KeyedProcessFunction):
    """
    Maintains per-room occupancy history in a plain Python dict (no Flink
    managed state / RocksDB).  History is lost on job restart but rebuilds
    within HISTORY_SLOTS events — acceptable for a warm-up period.
    
    Delegates predictions to the ML Prediction Service via HTTP.
    """

    def __init__(self):
        self._history: dict[str, list[float]] = {}
        self._predict_url: str = f"{PREDICTION_SERVICE_URL}/predict/congestion"

    def open(self, runtime_context: RuntimeContext):
        log.info("Prediction function ready, endpoint: %s", self._predict_url)

    def process_element(self, value: str, ctx):
        try:
            envelope = json.loads(value)
            # KafkaMessage envelope: {"message_id":..., "reading": {SensorReading}}
            reading = envelope.get("reading") or envelope
        except (json.JSONDecodeError, ValueError):
            return

        # Only process occupancy sensor data
        if reading.get("sensor_type") != "occupancy":
            return

        building_id = reading.get("building_id", "")
        room_type   = _infer_room_type(building_id)
        if room_type is None:
            return  # Not a canteen or library — skip

        room_id  = reading.get("room_id", "unknown")
        avg_val  = float(reading.get("value", 0.0))
        capacity = float(reading.get("capacity", 100.0))

        # Convert ts (unix ms) → ISO timestamp string
        ts_ms = reading.get("ts")
        if ts_ms:
            timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
        else:
            timestamp = datetime.now(tz=timezone.utc).isoformat()

        # Update in-process rolling history
        history = self._history.get(room_id, [])
        history.append(avg_val)
        if len(history) > HISTORY_SLOTS:
            history = history[-HISTORY_SLOTS:]
        self._history[room_id] = history

        # Skip if not enough history for lag features
        if len(history) < max(LAGS_NEEDED):
            return

        # Call prediction service
        payload = {
            "room_id":     room_id,
            "room_type":   room_type,
            "building_id": building_id,
            "timestamp":   timestamp,
            "avg":         avg_val,
            "capacity":    capacity,
            "history":     history,
            "context":     {},
        }

        try:
            body = json.dumps(payload).encode("utf-8")
            req  = urllib.request.Request(
                self._predict_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
            log.debug("Prediction for %s: %.2f (written=%s)",
                     room_id, result.get("predicted_avg"), result.get("written_to_influx"))
        except Exception as exc:
            log.warning("Prediction API call failed for room %s: %s", room_id, exc)

    def close(self):
        pass  # No external resources to release


# ── Flink job entrypoint ──────────────────────────────────────────────────────

def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    # parallelism=1: single operator owns all rooms — avoids splitting history
    # across slots and halves model-load memory vs parallelism=2.
    env.set_parallelism(1)

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BROKERS)
        .set_topics("sensors.occupancy")
        .set_group_id("ml-prediction-congestion")
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    stream = env.from_source(
        source,
        WatermarkStrategy.no_watermarks(),
        "KafkaOccupancySource",
    )

    (
        stream
        # key_by is still useful to guarantee ordering per room even at p=1
        .key_by(lambda s: json.loads(s).get("room_id", "unknown"))
        .process(CongestionPredictionFunction())
    )

    env.execute("SmartCampus Congestion Prediction")


if __name__ == "__main__":
    main()
