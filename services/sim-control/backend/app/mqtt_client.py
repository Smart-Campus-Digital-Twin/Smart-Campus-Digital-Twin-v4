from __future__ import annotations

import json
import logging
import os
import time
import uuid

import paho.mqtt.client as mqtt

logger = logging.getLogger("sim-control.mqtt")

MQTT_HOST = os.getenv("MQTT_HOST", "139.59.194.248")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

RECONNECT_DELAY_MAX = 30


class SimControlMQTT:
    def __init__(self) -> None:
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sim-control-{uuid.uuid4().hex[:8]}",
        )
        if MQTT_USERNAME:
            self._client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._connected = False

    def connect(self) -> None:
        delay = 1
        while True:
            try:
                self._client.connect(MQTT_HOST, MQTT_PORT, 60)
                self._client.loop_start()
                deadline = time.time() + 5
                while not self._connected and time.time() < deadline:
                    time.sleep(0.1)
                if self._connected:
                    return
            except Exception as exc:
                logger.warning(f"MQTT connect failed ({exc}), retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: dict) -> bool:
        if not self._connected:
            logger.warning("MQTT not connected — dropping message")
            return False
        data = json.dumps(payload)
        result = self._client.publish(topic, data, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"MQTT publish error rc={result.rc}")
            return False
        return True

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            self._connected = True
            logger.info(f"Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
        else:
            logger.error(f"MQTT connection refused, reason_code={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._connected = False
        logger.warning(f"Disconnected from MQTT broker, reason_code={reason_code}")
