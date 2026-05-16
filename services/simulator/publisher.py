import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt

from shared.logging_config import get_logger
from shared.models import SensorReading
from simulator.config import config

logger = get_logger("simulator.publisher", config.log_level)

_RECONNECT_DELAY_MAX = 30  # seconds


class MQTTPublisher:
    """Thread-safe MQTT publisher with automatic reconnection."""

    def __init__(self) -> None:
        transport = "websockets" if config.mqtt_port == 9001 else "tcp"
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"campus-simulator-{uuid.uuid4().hex[:8]}",
            transport=transport,
        )
        if config.mqtt_username:
            self._client.username_pw_set(config.mqtt_username, config.mqtt_password)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        delay = 1
        while True:
            try:
                self._client.connect(config.mqtt_host, config.mqtt_port, config.mqtt_keepalive)
                self._client.loop_start()
                # Wait up to 5 s for the CONNACK
                deadline = time.time() + 5
                while not self._connected and time.time() < deadline:
                    time.sleep(0.1)
                if self._connected:
                    return
            except Exception as exc:
                logger.warning(f"MQTT connect failed ({exc}), retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, _RECONNECT_DELAY_MAX)

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, reading: SensorReading) -> None:
        if not self._connected:
            logger.warning("MQTT not connected — dropping reading", extra={"sensor_id": reading.sensor_id})
            return
        result = self._client.publish(reading.mqtt_topic, reading.to_json(), qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"MQTT publish error rc={result.rc}", extra={"topic": reading.mqtt_topic})

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            self._connected = True
            logger.info("Connected to MQTT broker", extra={"host": config.mqtt_host, "port": config.mqtt_port})
        else:
            logger.error(f"MQTT connection refused, reason_code={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._connected = False
        logger.warning("Disconnected from MQTT broker", extra={"reason_code": reason_code})
