from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import SensorReadingOut
from .mqtt_client import SimControlMQTT
from .router import get_logs_store, get_rules_store, get_sensors_store, load_state, router
from .sensor_engine import SensorEngine

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sim-control.main")

PUBLISH_INTERVAL_S = float(os.getenv("PUBLISH_INTERVAL_S", "5.0"))

engine = SensorEngine()
mqtt = SimControlMQTT()
_stop_event = threading.Event()


def _build_mqtt_topic(reading: SensorReadingOut) -> str:
    return f"campus/{reading.building_id}/f{reading.floor}/{reading.room_id}/{reading.sensor_type}"


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_state()
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


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
