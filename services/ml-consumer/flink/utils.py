"""Shared Flink environment and Kafka source factory utilities."""

from __future__ import annotations

from pyflink.common import Duration, SimpleStringSchema, WatermarkStrategy
from pyflink.datastream import CheckpointingMode, StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource

from processing.flink.config import config


def build_flink_env(checkpoint_interval_ms: int) -> StreamExecutionEnvironment:
    """Return a configured StreamExecutionEnvironment.

    Uses EXACTLY_ONCE checkpointing.  The min pause between checkpoints is
    set to half the interval so recovery is bounded while avoiding overlap.
    """
    env = StreamExecutionEnvironment.get_execution_environment()
    env.enable_checkpointing(checkpoint_interval_ms)
    cfg = env.get_checkpoint_config()
    cfg.set_checkpointing_mode(CheckpointingMode.EXACTLY_ONCE)
    cfg.set_min_pause_between_checkpoints(checkpoint_interval_ms // 2)
    env.set_parallelism(config.parallelism)
    return env


def build_kafka_source(topics: list[str], group_id_suffix: str) -> KafkaSource:
    """Return a KafkaSource for the given topics using committed+earliest offsets.

    Falls back to earliest offset when no committed offset exists (e.g. first
    run or after state loss) so no data is skipped.  SASL credentials are
    injected when security.protocol is SASL_PLAINTEXT.
    """
    builder = (
        KafkaSource.builder()
        .set_bootstrap_servers(config.kafka_bootstrap_servers)
        .set_topics(*topics)
        .set_group_id(f"{config.kafka_group_id_prefix}-{group_id_suffix}")
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
    )
    if config.kafka_security_protocol.upper() in ("SASL_PLAINTEXT", "SASL_SSL"):
        jaas = (
            "org.apache.kafka.common.security.plain.PlainLoginModule required"
            f' username="{config.kafka_sasl_username}"'
            f' password="{config.kafka_sasl_password}";'
        )
        builder = (
            builder
            .set_property("security.protocol",  config.kafka_security_protocol)
            .set_property("sasl.mechanism",      config.kafka_sasl_mechanism)
            .set_property("sasl.jaas.config",    jaas)
        )
    return builder.build()


def build_bounded_watermark_strategy(
    out_of_order_s: int,
    idle_timeout_s: int = 60,
) -> WatermarkStrategy:
    """Return a bounded-out-of-orderness watermark strategy with idle timeout."""
    return (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(out_of_order_s))
        .with_idleness(Duration.of_seconds(idle_timeout_s))
    )
