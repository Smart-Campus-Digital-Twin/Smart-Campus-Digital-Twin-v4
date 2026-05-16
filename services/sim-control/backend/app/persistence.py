from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .models import LogEntry, Rule, Sensor

logger = logging.getLogger("sim-control.persistence")

DATA_DIR = Path(os.getenv("SIM_CONTROL_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
SENSORS_FILE = DATA_DIR / "sensors.json"
RULES_FILE = DATA_DIR / "rules.json"
LOGS_FILE = DATA_DIR / "logs.json"
MQTT_CONFIG_FILE = DATA_DIR / "mqtt_config.json"


def save_mqtt_config(config: dict) -> None:
    ensure_data_dir()
    with open(MQTT_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def load_mqtt_config() -> dict | None:
    if not MQTT_CONFIG_FILE.exists():
        return None
    with open(MQTT_CONFIG_FILE) as f:
        return json.load(f)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_sensors(sensors: dict[str, Sensor]) -> None:
    ensure_data_dir()
    data = {k: v.model_dump() for k, v in sensors.items()}
    with open(SENSORS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    logger.debug(f"Saved {len(data)} sensors to {SENSORS_FILE}")


def load_sensors() -> dict[str, Sensor]:
    if not SENSORS_FILE.exists():
        return {}
    with open(SENSORS_FILE) as f:
        data = json.load(f)
    return {k: Sensor(**v) for k, v in data.items()}


def save_rules(rules: dict[str, Rule]) -> None:
    ensure_data_dir()
    data = {k: v.model_dump() for k, v in rules.items()}
    with open(RULES_FILE, "w") as f:
        json.dump(data, f, indent=2)
    logger.debug(f"Saved {len(data)} rules to {RULES_FILE}")


def load_rules() -> dict[str, Rule]:
    if not RULES_FILE.exists():
        return {}
    with open(RULES_FILE) as f:
        data = json.load(f)
    return {k: Rule(**v) for k, v in data.items()}


def save_logs(logs: list[LogEntry]) -> None:
    ensure_data_dir()
    data = [l.model_dump() for l in logs[-5000:]]
    with open(LOGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_logs() -> list[LogEntry]:
    if not LOGS_FILE.exists():
        return []
    with open(LOGS_FILE) as f:
        data = json.load(f)
    return [LogEntry(**d) for d in data]
