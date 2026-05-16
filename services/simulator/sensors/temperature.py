"""
Indoor temperature sensor — Moratuwa, Sri Lanka tropical campus model.

── Moratuwa outdoor climate ────────────────────────────────────────────────────
  Coastal location (~6.8 °N), very high humidity.
  Daily outdoor cycle (sinusoidal, annual mean):
    Peak  ~31.5 °C at 14:00  (Mar–Apr hot season up to 33 °C)
    Trough ~24.5 °C at 02:00  (Dec–Jan cool season down to 23 °C)
    Daily half-swing: ± 3.5 °C  |  Mean: 28.0 °C

── Zone-specific HVAC profiles ─────────────────────────────────────────────────
  Each room type carries its own:
    setpoint   — HVAC cooling target (°C).  None = no central AC.
    occ_gain   — °C rise at 100 % room occupancy (body heat).
    equip_gain — °C rise from permanently-on equipment (labs, cooking).
    hvac_start / hvac_end — operating window (fractional hours).
    clamp_lo / clamp_hi   — hard physical bounds for the sensor.

  classroom  : HVAC 07:30–18:00, setpoint 23.5 °C, no equipment offset
  lab        : HVAC 07:30–18:00, setpoint 23.5 °C, +1.5 °C equipment load
  office     : HVAC 07:30–17:30, setpoint 23.0 °C, +0.5 °C (PCs, lighting)
  canteen    : HVAC 07:00–20:00, setpoint 25.0 °C, +4.0 °C cooking heat
  auditorium : HVAC 07:30–22:00, setpoint 23.5 °C  (events run late)
  library    : HVAC 07:30–20:00, setpoint 22.5 °C  (study comfort)
  hostel     : No central HVAC — window units / fans → tracks outdoor ambient
  server_room: 24/7 precision cooling, 20–22 °C

── Building-specific equipment heat offsets ────────────────────────────────────
  Stacked on top of the zone equip_gain for buildings with heavy heat sources:
    dept-chemical (+2.5 °C)  — industrial processes, fume hoods
    dept-material (+2.0 °C)  — furnaces, kilns, material testing rigs
    dept-mechanical (+1.5 °C) — machinery, workshops
    dept-ete (+1.0 °C)       — dense electronics benches
    sumanadasa (+1.0 °C)     — large computing / GPU labs
    faculty-it (+0.5 °C)     — compute labs + in-floor server load
    goda-canteen (+1.0 °C)   — larger commercial kitchen
    wala-canteen (+1.0 °C)   — larger commercial kitchen

── Night cooling ────────────────────────────────────────────────────────────────
  When HVAC shuts off, rooms drift toward the *outdoor ambient* via an
  Ornstein-Uhlenbeck process.  Because Moratuwa nights genuinely cool to
  24–26 °C the building steadily loses heat — the opposite of the old model
  which incorrectly used 29.5 °C as the night target.
  Drift coefficient θ = 0.04 (slow, reflecting building thermal mass).
"""

import math
import random
from typing import Any

from simulator.config import config

from .base import BaseSensor

_REF_INTERVAL = 5.0   # seconds — coefficients below are calibrated for this


# ── Moratuwa outdoor ambient ──────────────────────────────────────────────────

_OUTDOOR_MEAN      = 28.0   # °C annual mean outdoor temperature
_OUTDOOR_AMPLITUDE =  3.5   # °C half-swing (peak 14:00 → 31.5, trough 02:00 → 24.5)


def _outdoor_ambient(hour: float) -> float:
    """Sinusoidal daily outdoor temperature for Moratuwa.

    Peaks at 14:00 (~31.5 °C), troughs at 02:00 (~24.5 °C).
    cos(2π*(h−14)/24) = 1 at h=14, = −1 at h=2.
    """
    return _OUTDOOR_MEAN + _OUTDOOR_AMPLITUDE * math.cos(
        2 * math.pi * (hour - 14.0) / 24.0
    )


# ── Zone thermal profiles ─────────────────────────────────────────────────────
# (setpoint, occ_gain, equip_gain, hvac_start, hvac_end, clamp_lo, clamp_hi)
# setpoint = None  →  no central HVAC; room tracks outdoor ambient.

_ZP: dict[str, tuple] = {
    "classroom":  (23.5, 2.0, 0.0,  7.5,  18.0, 20.0, 32.0),
    "lab":        (23.5, 1.5, 1.5,  7.5,  18.0, 20.0, 34.0),
    "office":     (23.0, 1.0, 0.5,  7.5,  17.5, 20.0, 32.0),
    "canteen":    (25.0, 1.0, 4.0,  7.0,  20.0, 23.0, 36.0),
    "auditorium": (23.5, 2.5, 0.0,  7.5,  22.0, 20.0, 32.0),
    "library":    (22.5, 1.0, 0.0,  7.5,  20.0, 20.0, 30.0),
    "hostel":     (None, 0.5, 0.0,  None, None,  23.0, 35.0),
    "outdoor":    (None, 0.0, 0.0,  None, None,  22.0, 36.0),
    "server_room":(21.0, 0.0, 0.0,  0.0,  24.0, 18.0, 24.0),
}
_DEFAULT_PROFILE = _ZP["classroom"]


# ── Building-specific heat offsets (°C) ──────────────────────────────────────

_BUILDING_HEAT: dict[str, float] = {
    "dept-chemical":   2.5,
    "dept-material":   2.0,
    "dept-mechanical": 1.5,
    "dept-ete":        1.0,
    "sumanadasa":      1.0,
    "faculty-it":      0.5,
    "goda-canteen":    1.0,
    "wala-canteen":    1.0,
}


_HVAC_DEADBAND = 0.5   # °C half-band for thermostat hysteresis


class TemperatureSensor(BaseSensor):

    # Indoor HVAC cycle amplitude (°C half-swing).
    # sin peaks at 14:00 (peak solar load) → HVAC works hardest, slight indoor rise.
    HVAC_AMPLITUDE  = 1.5

    # Server room constants
    SERVER_SETPOINT  = 21.0
    SERVER_AMPLITUDE =  0.5

    # Sensor noise
    NOISE_SIGMA = 0.25   # °C

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        profile = _ZP.get(self.room_type, _DEFAULT_PROFILE)
        sp: float | None = profile[0]
        self._prev: float = sp if sp is not None else _outdoor_ambient(12.0)
        self._hvac_on: bool = False   # thermostat state (hysteresis)

    def _sample(self, context: dict[str, Any]) -> float:
        hour: float = context.get("hour", 12.0)
        occ:  float = context.get("occupancy_ratio", 0.0)

        if self.room_type == "server_room":
            return self._server_room(hour)

        profile = _ZP.get(self.room_type, _DEFAULT_PROFILE)
        setpoint, occ_gain, equip_gain, hvac_start, hvac_end, lo, hi = profile

        bld_heat    = _BUILDING_HEAT.get(self.building_id, 0.0)
        total_equip = equip_gain + bld_heat

        # Nonlinear occupancy heat gain: density matters more at high occupancy.
        # occ^1.5 underweights sparse crowds and overweights packed rooms.
        nonlinear_occ = occ ** 1.5

        if setpoint is None:
            # No central HVAC (hostel, outdoor): track outdoor ambient.
            # Asymmetric: solar gain warms faster (θ=0.07) than night cooling (θ=0.04).
            ambient = _outdoor_ambient(hour)
            theta   = 0.07 if ambient > self._prev else 0.04
            target  = ambient
        else:
            in_schedule = hvac_start <= hour < hvac_end
            cycle = self.HVAC_AMPLITUDE * math.sin(2 * math.pi * (hour - 8.0) / 24.0)
            comfort_target = setpoint + cycle + occ_gain * nonlinear_occ + total_equip

            if in_schedule:
                # Thermostat hysteresis: flip ON above setpoint+deadband,
                # flip OFF below setpoint-deadband; hold state in between.
                if self._prev >= setpoint + _HVAC_DEADBAND:
                    self._hvac_on = True
                elif self._prev <= setpoint - _HVAC_DEADBAND:
                    self._hvac_on = False

                if self._hvac_on:
                    target = comfort_target
                    # Asymmetric: HVAC cools quickly (θ=0.12), heats more slowly (θ=0.09).
                    theta  = 0.12 if self._prev > target else 0.09
                else:
                    # Thermostat satisfied — room drifts passively (thermal mass, slow).
                    target = _outdoor_ambient(hour)
                    theta  = 0.02
            else:
                # Outside operating hours: fully off, drift toward outdoor ambient.
                # Concrete holds heat so cooling (room > outdoor) is slower than heating.
                self._hvac_on = False
                target = _outdoor_ambient(hour)
                theta  = 0.04 if self._prev > target else 0.06

        dt_scale    = config.publish_interval_s / _REF_INTERVAL
        noise_sigma = self.NOISE_SIGMA * math.sqrt(dt_scale)
        self._prev += theta * dt_scale * (target - self._prev) + noise_sigma * random.gauss(0, 1)
        self._prev  = self._clamp(self._prev, lo=lo, hi=hi)
        return round(self._prev, 2)

    def _server_room(self, hour: float) -> float:
        load_cycle = self.SERVER_AMPLITUDE * math.sin(
            2 * math.pi * (hour - 14.0) / 24.0
        )
        noise = random.gauss(0, 0.10)
        v = self.SERVER_SETPOINT + load_cycle + noise
        return round(self._clamp(v, 18.0, 24.0), 2)
