from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .models import (
    BehaviorMode,
    LogEntry,
    Rule,
    RuleAction,
    RuleCondition,
    Sensor,
    SensorConfig,
    SensorType,
)
from .persistence import load_logs, load_rules, load_sensors, save_logs, save_rules, save_sensors

logger = logging.getLogger("sim-control.router")

router = APIRouter()

_sensors: dict[str, Sensor] = {}
_rules: dict[str, Rule] = {}
_logs: list[LogEntry] = []

SENSOR_TYPES = [t.value for t in SensorType]
BEHAVIOR_MODES = [m.value for m in BehaviorMode]


def _add_log(sensor_id: str, sensor_name: str, action: str, details: str = "", value: float | None = None) -> None:
    entry = LogEntry(
        sensor_id=sensor_id,
        sensor_name=sensor_name,
        action=action,
        details=details,
        value=value,
    )
    _logs.append(entry)
    if len(_logs) > 10000:
        del _logs[:2000]
    save_logs(_logs)


def _persist() -> None:
    save_sensors(_sensors)
    save_rules(_rules)


def load_state() -> None:
    global _sensors, _rules, _logs
    _sensors = load_sensors()
    _rules = load_rules()
    _logs = load_logs()
    logger.info(f"Loaded {len(_sensors)} sensors, {len(_rules)} rules, {len(_logs)} logs")


def get_sensors_store() -> dict[str, Sensor]:
    return _sensors


def get_rules_store() -> dict[str, Rule]:
    return _rules


def get_logs_store() -> list[LogEntry]:
    return _logs


@router.get("/sensors")
async def list_sensors(type: str | None = Query(None)):
    sensors = list(_sensors.values())
    if type and type in SENSOR_TYPES:
        sensors = [s for s in sensors if s.sensor_type == type]
    return {"sensors": sensors, "count": len(sensors)}


@router.post("/sensors")
async def create_sensor(sensor: Sensor):
    if sensor.id in _sensors:
        raise HTTPException(status_code=409, detail="Sensor already exists")
    _sensors[sensor.id] = sensor
    _persist()
    _add_log(sensor.id, sensor.name, "created", f"Sensor '{sensor.name}' created")
    logger.info(f"Sensor created: {sensor.id} ({sensor.name})")
    return sensor


@router.get("/sensors/{sensor_id}")
async def get_sensor(sensor_id: str):
    if sensor_id not in _sensors:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return _sensors[sensor_id]


@router.put("/sensors/{sensor_id}")
async def update_sensor(sensor_id: str, updates: dict[str, Any]):
    if sensor_id not in _sensors:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor = _sensors[sensor_id]
    changed: list[str] = []
    for key, val in updates.items():
        if key == "enabled" and isinstance(val, bool):
            sensor.enabled = val
            changed.append(f"enabled={val}")
        elif key == "behavior_mode" and val in BEHAVIOR_MODES:
            sensor.behavior_mode = BehaviorMode(val)
            changed.append(f"mode={val}")
        elif key == "name" and isinstance(val, str):
            sensor.name = val
            changed.append(f"name={val}")
        elif key == "config" and isinstance(val, dict):
            sensor.config = SensorConfig(**val)
            changed.append("config updated")
    sensor.updated_at = datetime.now(UTC).isoformat()
    _sensors[sensor_id] = sensor
    _persist()
    _add_log(sensor_id, sensor.name, "updated", ", ".join(changed))
    return sensor


@router.delete("/sensors/{sensor_id}")
async def delete_sensor(sensor_id: str):
    if sensor_id not in _sensors:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor = _sensors.pop(sensor_id)
    _persist()
    _add_log(sensor_id, sensor.name, "deleted", f"Sensor '{sensor.name}' deleted")
    return {"deleted": True}


@router.post("/sensors/{sensor_id}/toggle")
async def toggle_sensor(sensor_id: str):
    if sensor_id not in _sensors:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor = _sensors[sensor_id]
    sensor.enabled = not sensor.enabled
    sensor.updated_at = datetime.now(UTC).isoformat()
    _persist()
    _add_log(sensor_id, sensor.name, "toggled", f"enabled={sensor.enabled}")
    return {"sensor_id": sensor_id, "enabled": sensor.enabled}


@router.get("/rules")
async def list_rules():
    return {"rules": list(_rules.values()), "count": len(_rules)}


@router.post("/rules")
async def create_rule(rule: Rule):
    if rule.id in _rules:
        raise HTTPException(status_code=409, detail="Rule already exists")
    _rules[rule.id] = rule
    _persist()
    _add_log("", "", "rule_created", f"Rule '{rule.name}' created")
    return rule


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, updates: dict[str, Any]):
    if rule_id not in _rules:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = _rules[rule_id]
    for key, val in updates.items():
        if key == "enabled" and isinstance(val, bool):
            rule.enabled = val
        elif key == "name" and isinstance(val, str):
            rule.name = val
        elif key == "condition" and isinstance(val, dict):
            rule.condition = RuleCondition(**val)
        elif key == "action" and isinstance(val, dict):
            rule.action = RuleAction(**val)
    _rules[rule_id] = rule
    _persist()
    _add_log("", "", "rule_updated", f"Rule '{rule.name}' updated")
    return rule


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    if rule_id not in _rules:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = _rules.pop(rule_id)
    _persist()
    _add_log("", "", "rule_deleted", f"Rule '{rule.name}' deleted")
    return {"deleted": True}


@router.get("/logs")
async def list_logs(
    sensor_id: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    filtered = _logs
    if sensor_id:
        filtered = [l for l in filtered if l.sensor_id == sensor_id]
    if action:
        filtered = [l for l in filtered if l.action == action]
    total = len(filtered)
    page = filtered[offset : offset + limit]
    return {"logs": list(reversed(page)), "total": total, "limit": limit, "offset": offset}


@router.post("/seed")
async def seed_sensors():
    from .seed import generate_seed_sensors
    seeds = generate_seed_sensors()
    added = 0
    for sdata in seeds:
        sid = sdata["id"]
        if sid not in _sensors:
            _sensors[sid] = Sensor(**sdata)
            added += 1
    _persist()
    _add_log("", "", "seeded", f"Seeded {added} new sensors ({len(seeds)} total topology)")
    return {"seeded": added, "total_topology": len(seeds), "total_store": len(_sensors)}


@router.get("/status")
async def get_status():
    enabled = sum(1 for s in _sensors.values() if s.enabled)
    return {
        "total_sensors": len(_sensors),
        "enabled_sensors": enabled,
        "total_rules": len(_rules),
        "total_logs": len(_logs),
    }
