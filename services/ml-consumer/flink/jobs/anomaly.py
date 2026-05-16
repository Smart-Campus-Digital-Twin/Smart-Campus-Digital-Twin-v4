"""
Flink Job 3 — AnomalyJob
==========================
Rule-based anomaly detection on the real-time sensor stream.

Rules:
  1. temperature > 38 °C            → THRESHOLD_HIGH  / warning
  2. temperature < 14 °C            → THRESHOLD_LOW   / warning
  3. energy > 3× EMA rolling avg    → SPIKE           / warning   (stateful per room)
  4. occupancy > room_capacity×1.05 → CAPACITY_BREACH / critical  (room map loaded at startup)

Alert rules are loaded from PostgreSQL `alert_rules` at job startup.
Room capacities are loaded from PostgreSQL `rooms` at job startup and stored
in a plain dict broadcast to every AnomalyDetector instance.

Sinks:
  - Kafka topic `alerts.anomalies`   (JSON)
  - PostgreSQL table `anomalies`     (JDBC audit log)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import psycopg2
from pydantic import ValidationError
from pyflink.common import SimpleStringSchema, Types, Time as StateTime
from pyflink.datastream.connectors.kafka import (
    DeliveryGuarantee,
    KafkaRecordSerializationSchema,
    KafkaSink,
)
from pyflink.datastream.functions import KeyedProcessFunction, RuntimeContext
from pyflink.datastream.state import StateTtlConfig, ValueStateDescriptor

from processing.flink.config import config
from processing.flink.sinks.postgres_sink import PostgresBatchSink
from processing.flink.sinks.influx_sink import InfluxBatchSink
from processing.flink.utils import (
    build_bounded_watermark_strategy,
    build_flink_env,
    build_kafka_source,
)
from shared.db import get_db_connection
from shared.schemas import AnomalyEvent, KafkaMessage, SensorType
from shared.schemas.anomaly import Severity

logger = logging.getLogger(__name__)

_TOPICS = ["sensors.temperature", "sensors.occupancy", "sensors.energy"]

_ANOMALY_CHECKPOINT_MS = 60_000
_OUT_OF_ORDER_S        = 10
_IDLE_TIMEOUT_S        = 30

_EMA_ALPHA             = 0.3
_STATE_TTL_HOURS       = 24


# ---------------------------------------------------------------------------
# PostgreSQL loaders — called once at job startup
# ---------------------------------------------------------------------------

def _load_alert_rules() -> dict[tuple[str, str], dict]:
    """Return alert rules keyed by (sensor_type, anomaly_type).

    Falls back to hard-coded config defaults if PostgreSQL is unavailable.
    """
    try:
        conn = get_db_connection(config.database_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sensor_type, anomaly_type, threshold, severity "
                "FROM alert_rules WHERE enabled = true"
            )
            rules = {
                (row[0], row[1]): {"threshold": float(row[2]), "severity": row[3]}
                for row in cur.fetchall()
            }
        conn.close()
        logger.info("Loaded alert rules from PostgreSQL", extra={"count": len(rules)})
        return rules
    except psycopg2.OperationalError as exc:
        logger.warning(
            "Could not reach PostgreSQL for alert rules, using config defaults",
            extra={"reason": str(exc)},
        )
        return {
            ("temperature", "threshold_high"): {"threshold": config.temp_high_threshold,    "severity": "warning"},
            ("temperature", "threshold_low"):  {"threshold": config.temp_low_threshold,     "severity": "warning"},
            ("energy",      "spike"):          {"threshold": config.energy_spike_factor,    "severity": "warning"},
            ("occupancy",   "capacity_breach"):{"threshold": config.occupancy_cap_fraction, "severity": "critical"},
        }


def _load_room_capacities() -> dict[str, int]:
    """Return room capacities keyed by room_id, loaded from PostgreSQL at startup."""
    try:
        conn = get_db_connection(config.database_url)
        with conn.cursor() as cur:
            cur.execute("SELECT id, capacity FROM rooms")
            capacities = {row[0]: int(row[1]) for row in cur.fetchall()}
        conn.close()
        logger.info(
            "Loaded room capacities from PostgreSQL",
            extra={"count": len(capacities)},
        )
        return capacities
    except psycopg2.OperationalError as exc:
        logger.warning(
            "Could not reach PostgreSQL for room capacities; "
            "capacity_breach rule will be skipped",
            extra={"reason": str(exc)},
        )
        return {}


# ---------------------------------------------------------------------------
# Keyed process function — one instance per room_id key
# ---------------------------------------------------------------------------

class AnomalyDetector(KeyedProcessFunction):
    """Stateful per-room anomaly detector with EMA energy spike detection."""

    def __init__(
        self,
        alert_rules: dict[tuple[str, str], dict],
        room_capacities: dict[str, int],
    ) -> None:
        """Store startup-loaded lookup tables; state is initialised in open()."""
        self._alert_rules    = alert_rules
        self._room_capacities = room_capacities
        self._energy_avg_state: Optional[Any] = None

    def open(self, runtime_context: RuntimeContext) -> None:
        """Initialise keyed ValueState with a 24-hour TTL to prevent unbounded growth."""
        ttl_config = (
            StateTtlConfig
            .new_builder(StateTime.hours(_STATE_TTL_HOURS))
            .set_update_type(StateTtlConfig.UpdateType.OnReadAndWrite)
            .build()
        )
        descriptor = ValueStateDescriptor("energy_rolling_avg", Types.DOUBLE())
        descriptor.enable_time_to_live(ttl_config)
        self._energy_avg_state = runtime_context.get_state(descriptor)

    def process_element(self, reading: Any, ctx: Any):
        """Evaluate all applicable rules; yield one AnomalyEvent per violation."""
        yield from self._check(reading)

    def _check(self, reading: Any) -> list[AnomalyEvent]:
        """Apply all rules to one SensorReading; return list of detected anomalies."""
        results: list[AnomalyEvent] = []

        if reading.sensor_type == SensorType.TEMPERATURE:
            results.extend(self._check_temperature(reading))
        elif reading.sensor_type == SensorType.ENERGY:
            results.extend(self._check_energy_spike(reading))
        elif reading.sensor_type == SensorType.OCCUPANCY:
            results.extend(self._check_capacity(reading))

        return results

    def _check_temperature(self, reading: Any) -> list[AnomalyEvent]:
        """Evaluate high and low temperature threshold rules."""
        results: list[AnomalyEvent] = []
        rule_high = self._alert_rules.get(("temperature", "threshold_high"))
        rule_low  = self._alert_rules.get(("temperature", "threshold_low"))
        if rule_high and reading.value > rule_high["threshold"]:
            results.append(AnomalyEvent.threshold_breach(
                reading,
                threshold = rule_high["threshold"],
                high      = True,
                severity  = Severity(rule_high["severity"]),
            ))
        if rule_low and reading.value < rule_low["threshold"]:
            results.append(AnomalyEvent.threshold_breach(
                reading,
                threshold = rule_low["threshold"],
                high      = False,
                severity  = Severity(rule_low["severity"]),
            ))
        return results

    def _check_energy_spike(self, reading: Any) -> list[AnomalyEvent]:
        """Detect energy spikes using an exponential moving average."""
        rule = self._alert_rules.get(("energy", "spike"))
        if not rule:
            return []
        if self._energy_avg_state is None:
            logger.warning("Energy avg state not initialised — skipping spike check")
            return []
        _stored = self._energy_avg_state.value()
        current_avg: float = _stored if _stored is not None else reading.value
        new_avg = (1 - _EMA_ALPHA) * current_avg + _EMA_ALPHA * reading.value
        self._energy_avg_state.update(new_avg)
        if reading.value > current_avg * rule["threshold"]:
            return [AnomalyEvent.spike(
                reading,
                rolling_avg = current_avg,
                multiplier  = rule["threshold"],
            )]
        return []

    def _check_capacity(self, reading: Any) -> list[AnomalyEvent]:
        """Detect occupancy capacity breaches using the room capacity map."""
        rule = self._alert_rules.get(("occupancy", "capacity_breach"))
        if not rule:
            return []
        room_capacity = self._room_capacities.get(reading.room_id)
        if room_capacity is None:
            return []
        if reading.value > room_capacity * rule["threshold"]:
            return [AnomalyEvent.capacity_breach(
                reading,
                room_capacity = room_capacity,
            )]
        return []


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _parse_reading(raw: str) -> Any | None:
    """Deserialise one Kafka message; return SensorReading or None."""
    try:
        return KafkaMessage.from_json(raw).reading
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        logger.warning("Dropped unparseable message", extra={"reason": str(exc)})
        return None


def _parse_flat(raw: str) -> list:
    """Wrapper for flat_map: parse once, return list of zero or one result."""
    result = _parse_reading(raw)
    return [result] if result is not None else []


# ---------------------------------------------------------------------------
# Job entrypoint
# ---------------------------------------------------------------------------

def run() -> None:
    """Build and submit the AnomalyJob Flink job."""
    alert_rules      = _load_alert_rules()
    room_capacities  = _load_room_capacities()

    env    = build_flink_env(_ANOMALY_CHECKPOINT_MS)
    source = build_kafka_source(_TOPICS, "anomaly")

    raw_stream = env.from_source(
        source,
        build_bounded_watermark_strategy(_OUT_OF_ORDER_S, _IDLE_TIMEOUT_S),
        "KafkaSource[sensors.*]",
    )

    reading_stream = (
        raw_stream
        .flat_map(_parse_flat)
        .name("ParseReadings")
    )

    anomaly_stream = (
        reading_stream
        .key_by(lambda r: r.room_id)
        .process(AnomalyDetector(alert_rules, room_capacities))
        .name("AnomalyDetect")
    )

    # Sink 1 — Kafka alerts.anomalies
    kafka_sink_builder = (
        KafkaSink.builder()
        .set_bootstrap_servers(config.kafka_bootstrap_servers)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic("alerts.anomalies")
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
    )
    if config.kafka_security_protocol.upper() in ("SASL_PLAINTEXT", "SASL_SSL"):
        jaas = (
            "org.apache.kafka.common.security.plain.PlainLoginModule required"
            f' username="{config.kafka_sasl_username}"'
            f' password="{config.kafka_sasl_password}";'
        )
        kafka_sink_builder = (
            kafka_sink_builder
            .set_property("security.protocol", config.kafka_security_protocol)
            .set_property("sasl.mechanism",    config.kafka_sasl_mechanism)
            .set_property("sasl.jaas.config",  jaas)
        )
    anomaly_stream.map(lambda a: a.to_json(), output_type=Types.STRING()).sink_to(
        kafka_sink_builder.build()
    ).name("KafkaSink[alerts.anomalies]")

    # Sink 2 — PostgreSQL anomalies audit log (JDBC)
    jdbc_stream = anomaly_stream.map(
        lambda a: (
            a.anomaly_id,
            a.detected_at.isoformat(),
            a.sensor_id,
            a.building_id,
            a.floor,
            a.room_id,
            str(a.sensor_type),
            str(a.anomaly_type),
            str(a.severity),
            float(a.value),
            float(a.threshold),
            a.message,
        ),
        output_type=Types.ROW([
            Types.STRING(), Types.STRING(), Types.STRING(), Types.STRING(),
            Types.INT(),    Types.STRING(), Types.STRING(), Types.STRING(),
            Types.STRING(), Types.DOUBLE(), Types.DOUBLE(), Types.STRING(),
        ]),
    ).name("ToJdbcRow")
    # Pure-Python sinks in PyFlink must use map() (not add_sink which requires a
    # Java-backed SinkFunction). The returned DataStream[str] is intentionally unused.
    jdbc_stream.map(
        PostgresBatchSink(), output_type=Types.STRING()
    ).name("PostgreSQL[anomalies]")

    # Sink 3 — InfluxDB anomalies (for Grafana dashboards)
    anomaly_stream.map(
        lambda a: a.to_line_protocol(measurement="anomalies"),
        output_type=Types.STRING()
    ).map(
        InfluxBatchSink(
            bucket            = config.influxdb_bucket_raw,
            batch_size        = config.influx_batch_size,
            flush_interval_ms = config.influx_flush_ms,
        ),
        output_type=Types.STRING()
    ).name("InfluxDB[anomalies]")

    env.execute("AnomalyJob")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
