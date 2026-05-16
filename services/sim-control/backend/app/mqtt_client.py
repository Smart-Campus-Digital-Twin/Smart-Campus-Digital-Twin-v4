from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

logger = logging.getLogger("sim-control.mqtt")

RECONNECT_DELAY_MAX = 30
MESSAGE_BUFFER_LEN = 500


def env_defaults() -> dict:
    return {
        "host": os.getenv("MQTT_HOST", "139.59.194.248"),
        "port": int(os.getenv("MQTT_PORT", "1883")),
        "username": os.getenv("MQTT_USERNAME", ""),
        "password": os.getenv("MQTT_PASSWORD", ""),
        "tls_ca_cert": os.getenv("MQTT_TLS_CA_CERT", ""),
        "tls_client_cert": os.getenv("MQTT_TLS_CLIENT_CERT", ""),
        "tls_client_key": os.getenv("MQTT_TLS_CLIENT_KEY", ""),
    }


class SimControlMQTT:
    def __init__(self, config: dict | None = None) -> None:
        self._config = config or env_defaults()
        self._client: mqtt.Client | None = None
        self._connected = False
        self._stop = False
        self._lock = threading.Lock()
        self._messages: deque[dict] = deque(maxlen=MESSAGE_BUFFER_LEN)
        self._msg_counter = 0
        self._stats = {"sent": 0, "received": 0, "dropped": 0}

    def _build_client(self) -> mqtt.Client:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sim-control-{uuid.uuid4().hex[:8]}",
        )
        if self._config.get("username"):
            client.username_pw_set(self._config["username"], self._config.get("password", ""))
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    def connect(self) -> None:
        with self._lock:
            self._stop = False
            self._client = self._build_client()
            client = self._client
            host = self._config["host"]
            port = int(self._config["port"])
        delay = 1
        while not self._stop:
            try:
                client.connect(host, port, 60)
                client.loop_start()
                deadline = time.time() + 5
                while not self._connected and time.time() < deadline and not self._stop:
                    time.sleep(0.1)
                if self._connected:
                    return
                client.loop_stop()
            except Exception as exc:
                logger.warning(f"MQTT connect failed ({exc}), retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)

    def disconnect(self) -> None:
        with self._lock:
            self._stop = True
            client = self._client
            self._client = None
            self._connected = False
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass

    def reconfigure(self, new_config: dict) -> None:
        logger.info(f"Reconfiguring MQTT to {new_config.get('host')}:{new_config.get('port')}")
        self.disconnect()
        with self._lock:
            self._config = {**self._config, **new_config}
        threading.Thread(target=self.connect, daemon=True).start()

    def publish(self, topic: str, payload: dict) -> bool:
        if not self._connected or self._client is None:
            self._stats["dropped"] += 1
            self._record_message("dropped", topic, payload)
            logger.warning("MQTT not connected — dropping message")
            return False
        data = json.dumps(payload)
        result = self._client.publish(topic, data, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"MQTT publish error rc={result.rc}")
            self._stats["dropped"] += 1
            return False
        self._stats["sent"] += 1
        self._record_message("sent", topic, payload)
        return True

    def _record_message(self, direction: str, topic: str, payload: dict | str) -> None:
        self._msg_counter += 1
        self._messages.append({
            "seq": self._msg_counter,
            "direction": direction,
            "topic": topic,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    def get_messages(self, limit: int = 100, direction: str | None = None) -> list[dict]:
        msgs = list(self._messages)
        if direction:
            msgs = [m for m in msgs if m["direction"] == direction]
        return list(reversed(msgs[-limit:]))

    def get_stats(self) -> dict:
        return {**self._stats, "buffered": len(self._messages)}

    def clear_messages(self) -> None:
        self._messages.clear()
        self._msg_counter = 0
        self._stats = {"sent": 0, "received": 0, "dropped": 0}

    def get_config(self) -> dict:
        return dict(self._config)

    def status(self) -> dict:
        c = self._config
        return {
            "connected": self._connected,
            "host": c.get("host", ""),
            "port": int(c.get("port", 0)),
            "username": c.get("username", ""),
            "username_configured": bool(c.get("username")),
            "password_configured": bool(c.get("password")),
            "password_length": len(c.get("password", "")),
            "tls_enabled": bool(c.get("tls_ca_cert") or c.get("tls_client_cert") or c.get("tls_client_key")),
            "tls_ca_cert": c.get("tls_ca_cert", ""),
            "tls_client_cert": c.get("tls_client_cert", ""),
            "tls_client_key": c.get("tls_client_key", ""),
        }

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            self._connected = True
            logger.info(f"Connected to MQTT broker at {self._config['host']}:{self._config['port']}")
            try:
                client.subscribe("campus/#", qos=0)
                logger.info("Subscribed to campus/# for monitoring")
            except Exception as exc:
                logger.warning(f"Subscribe failed: {exc}")
        else:
            logger.error(f"MQTT connection refused, reason_code={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._connected = False
        logger.warning(f"Disconnected from MQTT broker, reason_code={reason_code}")

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload_str = msg.payload.decode("utf-8", errors="replace")
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                payload = payload_str
            self._stats["received"] += 1
            self._record_message("received", msg.topic, payload)
        except Exception as exc:
            logger.warning(f"on_message error: {exc}")
