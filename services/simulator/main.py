"""
Simulator entry point.

Context injected into every sensor tick
──────────────────────────────────────
  hour              float  fractional 24-h (Asia/Colombo)
  day_of_week       int    0=Mon … 6=Sun
  is_holiday        bool   Sri Lanka public holiday (from holidays.py)
  academic_day      AcademicDay  from AcademicCalendar (congestion, TUA, exam periods)
  active_venue_fill dict   {building_id: fill_factor} from EventCalendar
  occupancy_ratio   float  room's current count / capacity (fed into energy/temp)

Architecture
────────────
  - Zones (zones/ package) encapsulate zone-specific occupancy logic
  - Each room_type maps to a Zone class via get_zone_for_room_type()
  - Zones create their own sensors (temperature, occupancy, energy)
  - Zones apply academic calendar congestion to their occupancy patterns
"""
from __future__ import annotations

import dataclasses
import os
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from shared.logging_config import get_logger
from simulator.anomaly_injector import inject_if_enabled
from simulator.campus.academic_calendar import AcademicCalendar
from simulator.campus.academic_calendar import calendar as academic_calendar
from simulator.campus.events import EventCalendar
from simulator.campus.holidays import is_holiday
from simulator.campus.topology import CampusTopology, Room
from simulator.config import config
from simulator.publisher import MQTTPublisher
from simulator.sensors.base import BaseSensor
from simulator.sensors.occupancy import OccupancySensor
from simulator.zones import BaseZone, get_zone_for_room_type

logger = get_logger("simulator.main", config.log_level)

BUILDING_IDS: list[str] = sorted([
    'admin', 'dept-chemical', 'dept-civil', 'dept-design', 'dept-ete',
    'dept-material', 'dept-maths', 'dept-mechanical', 'dept-textile',
    'dept-transport', 'faculty-business', 'faculty-grad', 'faculty-it',
    'faculty-medicine', 'goda-canteen', 'hostel-a', 'hostel-c', 'l-canteen',
    'lagaan', 'library', 'multipurpose-hall', 'na-hall', 'registrar',
    'sentra-court', 'sumanadasa', 'wala-canteen',
])


def _build_zones(topology: CampusTopology) -> list[tuple[Room, BaseZone]]:
    zones: list[tuple[Room, BaseZone]] = []
    for room in topology.all_rooms():
        zone_class = get_zone_for_room_type(room.room_type)
        zone = zone_class(room)
        zones.append((room, zone))
    return zones


def _make_context(
    now: datetime,
    event_calendar: EventCalendar,
    academic_calendar: AcademicCalendar,
) -> dict:
    hour = now.hour + now.minute / 60.0
    today = now.date()
    academic_day = academic_calendar.get_day(today)

    return {
        "hour":               hour,
        "day_of_week":        now.weekday(),
        "is_holiday":         is_holiday(today),
        "academic_day":       academic_day,
        "active_venue_fill":  event_calendar.active_venue_fill(today, hour),
        "active_event_types": event_calendar.active_event_types(today, hour),
    }


app = FastAPI(title="Simulator Control UI")
simulator_state: dict[str, Any] = {
    "running": True,
    "reading_count": 0,
    "interval_s": config.publish_interval_s,
    "anomaly_prob": float(os.environ.get("ANOMALY_INJECTION_PROB", "0.01")),
    # {building_id: {temperature, occupancy, energy, ticks_remaining}}
    "overrides": {},
    "disabled_sensors": set(),  # NEW: set of sensor_id strings that should be skipped
}


def _apply_override(reading: Any, overrides: dict) -> Any:
    ov = overrides.get(reading.building_id)
    if not ov or ov.get("ticks_remaining", 0) <= 0:
        return reading
    val = ov.get(reading.sensor_type)
    if val is None:
        return reading
    return dataclasses.replace(reading, value=float(val))


def main_loop():
    logger.info("Starting Smart Campus Simulator (Zone-based with Academic Calendar)")
    topology  = CampusTopology()
    publisher = MQTTPublisher()
    publisher.connect()

    event_calendar = EventCalendar()
    academic_cal = academic_calendar

    zones = _build_zones(topology)

    all_sensors: list[tuple[Room, BaseSensor]] = []
    for room, zone in zones:
        for sensor in zone.sensors:
            all_sensors.append((room, sensor))

    reading_count = 0

    logger.info(
        "Simulator ready",
        extra={
            "zone_count":     len(zones),
            "sensor_count":   len(all_sensors),
            "building_count": len(topology.buildings),
            "room_count":     len(topology.all_rooms()),
            "interval_s":     config.publish_interval_s,
        },
    )

    simulator_state["all_sensor_ids"] = [s.sensor_id for _, s in all_sensors]

    while True:
        if not simulator_state["running"]:
            time.sleep(1)
            continue

        now = datetime.now(ZoneInfo(config.campus_timezone))
        ctx = _make_context(now, event_calendar, academic_cal)
        today = now.date()
        academic_day = academic_cal.get_day(today)

        occ_readings:  dict[str, float]  = {}
        occ_published: dict[str, object] = {}
        for room, sensor in all_sensors:
            if sensor.sensor_id in simulator_state["disabled_sensors"]:
                continue
            if sensor.sensor_type == "occupancy" and isinstance(sensor, OccupancySensor):
                r = sensor.read(ctx)
                if r is not None:
                    r = _apply_override(r, simulator_state["overrides"])
                    occ_readings[room.room_id]      = r.value / max(1, sensor.capacity)
                    occ_published[sensor.sensor_id] = r

        for room, sensor in all_sensors:
            if sensor.sensor_id in simulator_state["disabled_sensors"]:
                continue
            if sensor.sensor_id in occ_published:
                reading = occ_published[sensor.sensor_id]
            else:
                room_ctx = {**ctx, "occupancy_ratio": occ_readings.get(room.room_id, 0.0)}
                reading  = sensor.read(room_ctx)
            if reading is not None:
                reading = _apply_override(reading, simulator_state["overrides"])
                reading = inject_if_enabled(reading)
                publisher.publish(reading)
                reading_count += 1

        # Decrement override tick counters once per full cycle
        expired = [bld for bld, ov in simulator_state["overrides"].items()
                   if ov.get("ticks_remaining", 0) <= 1]
        for bld in expired:
            del simulator_state["overrides"][bld]
        for ov in simulator_state["overrides"].values():
            ov["ticks_remaining"] = max(0, ov.get("ticks_remaining", 0) - 1)

        if reading_count % (len(all_sensors) * 10) == 0:
            events_today = event_calendar.events_for_date(today)
            logger.info(
                "Heartbeat",
                extra={
                    "total_readings":   reading_count,
                    "is_holiday":       is_holiday(today),
                    "activity":         academic_day.activity.value,
                    "congestion":       round(academic_day.congestion_fraction, 2),
                    "tua_active":       academic_day.tua_active,
                    "events_today":     len(events_today),
                    "active_venues":    list(ctx["active_venue_fill"].keys()),
                },
            )

        simulator_state["reading_count"] = reading_count
        time.sleep(simulator_state["interval_s"])

    publisher.disconnect()
    logger.info("Simulator stopped", extra={"total_readings": reading_count})


# ── Pydantic request models ──────────────────────────────────────────────────

class IntervalRequest(BaseModel):
    value: float

class AnomalyProbRequest(BaseModel):
    value: float

class OverrideRequest(BaseModel):
    temperature: float | None = None
    occupancy: float | None = None
    energy: float | None = None
    duration_ticks: int = 20


# ── REST API ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def get_ui():
    overrides_rows = ""
    for bld, ov in simulator_state["overrides"].items():
        t = ov.get("temperature", "—")
        o = ov.get("occupancy",   "—")
        e = ov.get("energy",      "—")
        r = ov.get("ticks_remaining", 0)
        overrides_rows += f"""
        <tr>
          <td>{bld}</td>
          <td>{f"{t}°C" if t != "—" else "—"}</td>
          <td>{f"{o} ppl" if o != "—" else "—"}</td>
          <td>{f"{e} W" if e != "—" else "—"}</td>
          <td>{r} ticks</td>
          <td><button onclick="clearOverride('{bld}')" class="btn-sm btn-danger">Clear</button></td>
        </tr>"""

    building_options = "\n".join(
        f'<option value="{b}">{b}</option>' for b in BUILDING_IDS
    )

    status_class = "status-running" if simulator_state["running"] else "status-stopped"
    status_text  = "SYSTEM ONLINE" if simulator_state["running"] else "SYSTEM OFFLINE"
    btn_text     = "SHUT DOWN" if simulator_state["running"] else "INITIALIZE"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Campus Simulator Control Panel</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0B0C10; --panel: rgba(31,40,51,0.85);
      --text: #C5C6C7; --accent: #66FCF1; --accent-dark: #45A29E;
      --danger: #e53e3e; --warn: #F5A623;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: radial-gradient(circle at 30% 20%, #111a22 0%, var(--bg) 100%);
      color: var(--text); min-height: 100vh; padding: 24px;
    }}
    h1 {{ color: var(--accent); font-weight: 800; letter-spacing: 1.5px;
          text-transform: uppercase; font-size: 20px; margin-bottom: 24px; }}
    h2 {{ color: var(--accent); font-size: 13px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(340px,1fr));
             gap: 16px; max-width: 1200px; margin: 0 auto; }}
    .card {{
      background: var(--panel); backdrop-filter: blur(16px);
      border: 1px solid rgba(102,252,241,0.2); border-radius: 16px; padding: 20px;
    }}
    .status-bar {{ display: flex; align-items: center; gap: 10px;
                   font-weight: 700; font-size: 16px; margin-bottom: 16px; }}
    .dot {{ width: 12px; height: 12px; border-radius: 50%;
            box-shadow: 0 0 8px currentColor; }}
    .status-running {{ color: #00ff00; background: #00ff00; }}
    .status-stopped {{ color: #ff4444; background: #ff4444; }}
    .stats {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
    .stat {{ background: rgba(0,0,0,0.3); padding: 10px 14px; border-radius: 10px;
             border: 1px solid rgba(102,252,241,0.1); flex: 1; min-width: 100px; }}
    .stat-val {{ font-size: 22px; font-weight: 800; color: #fff; }}
    .stat-lbl {{ font-size: 10px; text-transform: uppercase; color: var(--accent-dark);
                 font-weight: 600; margin-top: 2px; }}
    .btn {{
      background: linear-gradient(135deg, var(--accent-dark), var(--accent));
      color: var(--bg); border: none; padding: 10px 28px;
      font-size: 13px; font-weight: 800; border-radius: 24px; cursor: pointer;
      text-transform: uppercase; letter-spacing: 1px;
      transition: transform .2s, box-shadow .2s;
    }}
    .btn:hover {{ transform: scale(1.04); box-shadow: 0 4px 16px rgba(102,252,241,0.4); }}
    .btn-sm {{ padding: 4px 12px; font-size: 11px; border-radius: 8px;
               border: none; cursor: pointer; font-weight: 700; }}
    .btn-danger {{ background: var(--danger); color: #fff; }}
    .btn-warn {{ background: var(--warn); color: #000; }}
    .btn-accent {{ background: var(--accent); color: var(--bg); }}
    label {{ font-size: 11px; font-weight: 600; text-transform: uppercase;
             letter-spacing: .5px; color: var(--accent-dark); display: block;
             margin-bottom: 4px; margin-top: 10px; }}
    input[type=number], select {{
      width: 100%; background: rgba(0,0,0,0.4); border: 1px solid rgba(102,252,241,0.25);
      border-radius: 8px; padding: 8px 10px; color: #fff; font-size: 13px;
      outline: none;
    }}
    input[type=range] {{
      width: 100%; accent-color: var(--accent); height: 4px;
    }}
    .range-row {{ display: flex; align-items: center; gap: 10px; }}
    .range-val {{ color: var(--accent); font-weight: 700; font-size: 13px;
                  min-width: 48px; text-align: right; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th {{ color: var(--accent-dark); font-size: 10px; text-transform: uppercase;
          padding: 6px 8px; border-bottom: 1px solid rgba(102,252,241,0.15);
          text-align: left; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid rgba(102,252,241,0.07);
          color: #ddd; }}
    .empty {{ color: #555; font-style: italic; font-size: 12px;
              padding: 12px 0; text-align: center; }}
    .quick-btns {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .msg {{ font-size: 11px; color: var(--accent); margin-top: 6px;
            min-height: 16px; }}
  </style>
</head>
<body>
  <h1>&#9881; Campus Simulator Control Panel</h1>

  <div class="grid">

    <!-- ── System status ─────────────────────────── -->
    <div class="card">
      <h2>System Status</h2>
      <div class="status-bar">
        <span class="dot {status_class}"></span>
        {status_text}
      </div>
      <div class="stats">
        <div class="stat">
          <div class="stat-val" id="readingCount">{simulator_state['reading_count']}</div>
          <div class="stat-lbl">Total Readings</div>
        </div>
        <div class="stat">
          <div class="stat-val" id="intervalVal">{simulator_state['interval_s']}s</div>
          <div class="stat-lbl">Tick Interval</div>
        </div>
        <div class="stat">
          <div class="stat-val" id="overrideCount">{len(simulator_state['overrides'])}</div>
          <div class="stat-lbl">Active Overrides</div>
        </div>
      </div>
      <button class="btn" onclick="toggleSim()">{btn_text}</button>
    </div>

    <!-- ── Tick / anomaly config ──────────────────── -->
    <div class="card">
      <h2>Simulation Config</h2>
      <label>Tick Interval (seconds)</label>
      <div class="range-row">
        <input type="range" id="intervalSlider" min="1" max="30" step="0.5"
               value="{simulator_state['interval_s']}"
               oninput="document.getElementById('intervalDisplay').innerText=this.value+'s'">
        <span class="range-val" id="intervalDisplay">{simulator_state['interval_s']}s</span>
      </div>
      <button class="btn-sm btn-accent" style="margin-top:8px"
              onclick="setInterval_()">Apply Interval</button>
      <div class="msg" id="intervalMsg"></div>

      <label>Anomaly Injection Probability</label>
      <div class="range-row">
        <input type="range" id="anomalySlider" min="0" max="0.5" step="0.01"
               value="{simulator_state['anomaly_prob']}"
               oninput="document.getElementById('anomalyDisplay').innerText=(+this.value*100).toFixed(0)+'%'">
        <span class="range-val" id="anomalyDisplay">{round(simulator_state['anomaly_prob']*100)}%</span>
      </div>
      <button class="btn-sm btn-accent" style="margin-top:8px"
              onclick="setAnomaly()">Apply Anomaly Prob</button>
      <div class="msg" id="anomalyMsg"></div>
    </div>

    <!-- ── Quick actions ─────────────────────────── -->
    <div class="card">
      <h2>Quick Actions</h2>
      <div class="quick-btns">
        <button class="btn-sm btn-accent"
                onclick="quickOverride('all', {{temperature:38,occupancy:200,energy:5000}}, 30)">
          🔥 Max All (30 ticks)
        </button>
        <button class="btn-sm btn-accent"
                onclick="quickOverride('all', {{temperature:21,occupancy:0,energy:50}}, 30)">
          ❄️ Empty All (30 ticks)
        </button>
        <button class="btn-sm btn-warn"
                onclick="quickOverride('all', {{temperature:35,occupancy:150,energy:3000}}, 20)">
          ⚠️ Busy All (20 ticks)
        </button>
        <button class="btn-sm btn-danger" onclick="clearAllOverrides()">
          🗑️ Clear All Overrides
        </button>
        <button class="btn-sm btn-accent" onclick="setInterval_v(1)">⚡ Fast (1s)</button>
        <button class="btn-sm btn-accent" onclick="setInterval_v(5)">⏱ Normal (5s)</button>
        <button class="btn-sm btn-accent" onclick="setInterval_v(15)">🐢 Slow (15s)</button>
      </div>
    </div>

    <!-- ── Building override ──────────────────────── -->
    <div class="card">
      <h2>Building Override</h2>
      <label>Building</label>
      <select id="ovBuilding">
        <option value="">-- select building --</option>
        {building_options}
      </select>
      <label>Temperature (°C) — leave blank to keep simulated</label>
      <input type="number" id="ovTemp" placeholder="e.g. 36.5" step="0.5">
      <label>Occupancy (people count)</label>
      <input type="number" id="ovOcc" placeholder="e.g. 200" min="0">
      <label>Energy (Watts)</label>
      <input type="number" id="ovEnergy" placeholder="e.g. 4500" min="0">
      <label>Duration (ticks)</label>
      <input type="number" id="ovTicks" value="20" min="1" max="200">
      <button class="btn-sm btn-accent" style="margin-top:12px"
              onclick="applyOverride()">Apply Override</button>
      <div class="msg" id="overrideMsg"></div>
    </div>

    <!-- ── Active overrides table ────────────────── -->
    <div class="card" style="grid-column: 1 / -1">
      <h2>Active Overrides</h2>
      <div id="overridesTableWrap">
        <table>
          <thead>
            <tr><th>Building</th><th>Temp</th><th>Occupancy</th><th>Energy</th><th>Ticks Left</th><th></th></tr>
          </thead>
          <tbody id="overridesBody">
            {"<tr><td colspan='6' class='empty'>No active overrides</td></tr>" if not overrides_rows else overrides_rows}
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Sensors List ────────────────── -->
    <div class="card" style="grid-column: 1 / -1">
      <h2>Sensors</h2>
      <input id="sensorFilter" placeholder="filter by id..." oninput="filterSensors(this.value)" style="width:100%; max-width:300px; padding:4px;">
      <div id="sensorList" style="max-height: 320px; overflow-y: auto; margin-top: 8px"></div>
    </div>

  </div>

  <script>
    async function post(url, body={{}}
) {{
      const r = await fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(body)}});
      return r.json();
    }}
    async function del_(url) {{
      const r = await fetch(url, {{method:'DELETE'}});
      return r.json();
    }}

    async function toggleSim() {{
      await post('/toggle');
      location.reload();
    }}

    async function setInterval_() {{
      const v = parseFloat(document.getElementById('intervalSlider').value);
      await post('/config/interval', {{value: v}});
      document.getElementById('intervalMsg').innerText = `Interval set to ${{v}}s`;
      document.getElementById('intervalVal').innerText = v + 's';
    }}

    async function setInterval_v(v) {{
      await post('/config/interval', {{value: v}});
      document.getElementById('intervalSlider').value = v;
      document.getElementById('intervalDisplay').innerText = v + 's';
      document.getElementById('intervalVal').innerText = v + 's';
      document.getElementById('intervalMsg').innerText = `Interval set to ${{v}}s`;
    }}

    async function setAnomaly() {{
      const v = parseFloat(document.getElementById('anomalySlider').value);
      await post('/config/anomaly_prob', {{value: v}});
      document.getElementById('anomalyMsg').innerText = `Anomaly prob set to ${{(v*100).toFixed(0)}}%`;
    }}

    async function applyOverride() {{
      const bld = document.getElementById('ovBuilding').value;
      if (!bld) {{ alert('Select a building'); return; }}
      const t  = document.getElementById('ovTemp').value;
      const o  = document.getElementById('ovOcc').value;
      const e  = document.getElementById('ovEnergy').value;
      const tk = parseInt(document.getElementById('ovTicks').value) || 20;
      const body = {{ duration_ticks: tk }};
      if (t !== '') body.temperature = parseFloat(t);
      if (o !== '') body.occupancy = parseFloat(o);
      if (e !== '') body.energy = parseFloat(e);
      await post(`/override/${{bld}}`, body);
      document.getElementById('overrideMsg').innerText = `Override applied to ${{bld}} for ${{tk}} ticks`;
      setTimeout(() => location.reload(), 800);
    }}

    async function clearOverride(bld) {{
      await del_(`/override/${{bld}}`);
      location.reload();
    }}

    async function clearAllOverrides() {{
      await post('/override/clear-all');
      location.reload();
    }}

    async function quickOverride(target, vals, ticks) {{
      if (target === 'all') {{
        const buildings = {list(BUILDING_IDS)};
        for (const bld of buildings) {{
          await post(`/override/${{bld}}`, {{...vals, duration_ticks: ticks}});
        }}
      }} else {{
        await post(`/override/${{target}}`, {{...vals, duration_ticks: ticks}});
      }}
      location.reload();
    }}

    // Auto-refresh stats every 5s without full page reload
    async function refreshStats() {{
      try {{
        const r = await fetch('/status');
        const d = await r.json();
        document.getElementById('readingCount').innerText = d.reading_count;
        document.getElementById('intervalVal').innerText  = d.interval_s + 's';
        document.getElementById('overrideCount').innerText = d.active_overrides.length;
      }} catch(e) {{}}
    }}
    setInterval(refreshStats, 5000);

    async function loadSensors() {{
      const r = await fetch('/sensors');
      const d = await r.json();
      const list = document.getElementById('sensorList');
      list.innerHTML = d.sensors.map(s =>
        `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #333">
          <span>${{s.sensor_id}}</span>
          <button class="btn-sm ${{s.enabled ? 'btn-danger' : 'btn-accent'}}"
                  style="border:none; border-radius:4px; cursor:pointer;"
                  onclick="toggleSensor('${{s.sensor_id}}', ${{!s.enabled}})">
            ${{s.enabled ? 'Disable' : 'Enable'}}
          </button>
        </div>`
      ).join('');
    }}
    async function toggleSensor(id, enable) {{
      await post(`/sensor/${{id}}/${{enable ? 'enable' : 'disable'}}`);
      loadSensors();
    }}
    function filterSensors(q) {{
      q = q.toLowerCase();
      for (const row of document.querySelectorAll('#sensorList > div')) {{
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
      }}
    }}
    loadSensors();
    setInterval(loadSensors, 10000);
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@app.post("/toggle")
async def toggle_sim():
    simulator_state["running"] = not simulator_state["running"]
    return {"running": simulator_state["running"]}


@app.post("/config/interval")
async def set_interval(req: IntervalRequest):
    simulator_state["interval_s"] = max(0.5, min(60.0, req.value))
    return {"interval_s": simulator_state["interval_s"]}


@app.post("/config/anomaly_prob")
async def set_anomaly_prob(req: AnomalyProbRequest):
    simulator_state["anomaly_prob"] = max(0.0, min(1.0, req.value))
    return {"anomaly_prob": simulator_state["anomaly_prob"]}


@app.post("/override/{building_id}")
async def set_override(building_id: str, req: OverrideRequest):
    if building_id not in BUILDING_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown building: {building_id}")
    simulator_state["overrides"][building_id] = {
        "temperature":      req.temperature,
        "occupancy":        req.occupancy,
        "energy":           req.energy,
        "ticks_remaining":  max(1, req.duration_ticks),
    }
    return {"building_id": building_id, "override": simulator_state["overrides"][building_id]}


@app.post("/override/clear-all")
async def clear_all_overrides():
    simulator_state["overrides"].clear()
    return {"cleared": True}


@app.delete("/override/{building_id}")
async def clear_override(building_id: str):
    removed = simulator_state["overrides"].pop(building_id, None)
    return {"removed": removed is not None}


@app.get("/overrides")
async def list_overrides():
    return simulator_state["overrides"]

class SensorToggleRequest(BaseModel):
    enabled: bool

@app.post("/sensor/{sensor_id}/enable")
async def enable_sensor(sensor_id: str):
    simulator_state["disabled_sensors"].discard(sensor_id)
    return {"sensor_id": sensor_id, "enabled": True}

@app.post("/sensor/{sensor_id}/disable")
async def disable_sensor(sensor_id: str):
    simulator_state["disabled_sensors"].add(sensor_id)
    return {"sensor_id": sensor_id, "enabled": False}

@app.get("/sensors")
async def list_sensors():
    return {
        "sensors": [
            {"sensor_id": s_id, "enabled": s_id not in simulator_state["disabled_sensors"]}
            for s_id in simulator_state.get("all_sensor_ids", [])
        ]
    }

@app.get("/status")
async def get_status():
    return {
        "running":         simulator_state["running"],
        "reading_count":   simulator_state["reading_count"],
        "interval_s":      simulator_state["interval_s"],
        "anomaly_prob":    simulator_state["anomaly_prob"],
        "active_overrides": list(simulator_state["overrides"].keys()),
    }


def main() -> None:
    t = threading.Thread(target=main_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
