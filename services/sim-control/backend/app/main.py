from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import Sensor, SensorReadingOut
from .mqtt_client import SimControlMQTT, env_defaults
from .persistence import load_mqtt_config, save_mqtt_config
from .router import get_logs_store, get_rules_store, get_sensors_store, load_state, router
from .sensor_engine import SensorEngine

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sim-control.main")

PUBLISH_INTERVAL_S = float(os.getenv("PUBLISH_INTERVAL_S", "5.0"))


def _initial_mqtt_config() -> dict:
    persisted = load_mqtt_config()
    if persisted:
        return {**env_defaults(), **persisted}
    return env_defaults()


engine = SensorEngine()
mqtt = SimControlMQTT(_initial_mqtt_config())
_stop_event = threading.Event()


def _build_mqtt_topic(reading: SensorReadingOut) -> str:
    return f"campus/{reading.sensor_type}"


def _apply_rules(reading: SensorReadingOut) -> SensorReadingOut:
    rules = get_rules_store()
    for rule in rules.values():
        if not rule.enabled:
            continue
        cond = rule.condition
        if cond.sensor_id != reading.sensor_id:
            continue
        op = cond.operator
        triggered = False
        if op == "gt":
            triggered = reading.value > cond.threshold
        elif op == "lt":
            triggered = reading.value < cond.threshold
        elif op == "gte":
            triggered = reading.value >= cond.threshold
        elif op == "lte":
            triggered = reading.value <= cond.threshold
        elif op == "eq":
            triggered = abs(reading.value - cond.threshold) < 0.001
        if not triggered:
            continue
        action = rule.action
        if action.type == "set_value":
            reading.value = action.value
            reading.metadata["rule_triggered"] = rule.name
        elif action.type == "toggle" and action.target_sensor_id:
            sensors = get_sensors_store()
            if action.target_sensor_id in sensors:
                sensors[action.target_sensor_id].enabled = action.enable if action.enable is not None else not sensors[action.target_sensor_id].enabled
    return reading


def _publish_loop() -> None:
    logger.info("Starting sim-control publish loop")
    mqtt.connect()
    while not _stop_event.is_set():
        sensors = get_sensors_store()
        for sensor in sensors.values():
            reading = engine.generate_reading(sensor)
            if reading is None:
                continue
            reading = _apply_rules(reading)
            topic = _build_mqtt_topic(reading)
            mqtt.publish(topic, reading.model_dump())
        _stop_event.wait(PUBLISH_INTERVAL_S)
    mqtt.disconnect()
    logger.info("Publish loop stopped")


def _autoseed_if_empty() -> None:
    store = get_sensors_store()
    if store:
        return
    try:
        from .seed import generate_seed_sensors
        seeds = generate_seed_sensors()
        for sdata in seeds:
            store[sdata["id"]] = Sensor(**sdata)
        from .persistence import save_sensors
        save_sensors(store)
        logger.info(f"Auto-seeded {len(seeds)} sensors from campus topology")
    except Exception as exc:
        logger.error(f"Auto-seed failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_state()
    _autoseed_if_empty()
    thread = threading.Thread(target=_publish_loop, daemon=True)
    thread.start()
    logger.info("Sim-Control backend started")
    yield
    _stop_event.set()
    logger.info("Sim-Control backend shutting down")


app = FastAPI(title="Simulator Control Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sim-control"}


@app.get("/api/config")
async def config():
    return {
        "mqtt": mqtt.status(),
        "publish_interval_s": PUBLISH_INTERVAL_S,
        "topics": {
            "temperature": "campus/temperature",
            "occupancy": "campus/occupancy",
            "energy": "campus/energy",
        },
    }


@app.get("/api/readings")
async def sensor_values():
    return engine.values_snapshot()


@app.get("/api/readings/{sensor_id}")
async def sensor_last_reading(sensor_id: str):
    r = engine.get_last_reading(sensor_id)
    if r is None:
        return {"sensor_id": sensor_id, "reading": None}
    return {"sensor_id": sensor_id, "reading": r}


@app.get("/api/readings/{sensor_id}/history")
async def sensor_history(sensor_id: str):
    hist = engine.get_history(sensor_id)
    return {
        "sensor_id": sensor_id,
        "points": [{"t": t, "v": v} for t, v in hist],
        "count": len(hist),
    }


@app.get("/api/mqtt/messages")
async def mqtt_messages(limit: int = 100, direction: str | None = None):
    return {"messages": mqtt.get_messages(limit=limit, direction=direction), "stats": mqtt.get_stats()}


@app.delete("/api/mqtt/messages")
async def mqtt_messages_clear():
    mqtt.clear_messages()
    return {"cleared": True}


class MqttConfigIn(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    tls_ca_cert: str | None = None
    tls_client_cert: str | None = None
    tls_client_key: str | None = None


@app.get("/api/mqtt/config")
async def get_mqtt_config():
    cfg = mqtt.get_config()
    cfg = {**cfg, "password": "***" if cfg.get("password") else ""}
    return cfg


@app.put("/api/mqtt/config")
async def update_mqtt_config(body: MqttConfigIn):
    current = mqtt.get_config()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    new_cfg = {**current, **updates}
    save_mqtt_config(new_cfg)
    mqtt.reconfigure(new_cfg)
    return {"updated": True, "status": mqtt.status()}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
