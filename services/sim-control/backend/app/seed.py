"""
Seed script: generates sim-control sensors from the campus topology.
Matches the original simulator sensor IDs: {room_id}-{sensor_type}
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from simulator.campus.topology import CampusTopology, STANDARD, OUTDOOR, SERVER

TYPE_CONFIGS = {
    "temperature": {"min_value": 18, "max_value": 38, "interval_ms": 5000, "pattern": [], "anomaly_prob": 0.05},
    "occupancy":   {"min_value": 0,  "max_value": 100, "interval_ms": 5000, "pattern": [], "anomaly_prob": 0.05},
    "energy":      {"min_value": 0,  "max_value": 500, "interval_ms": 5000, "pattern": [], "anomaly_prob": 0.05},
}

ROOM_TYPE_DEFAULTS = {
    "classroom":    {"temperature": (22, 32), "occupancy": (0, 80),  "energy": (50, 300)},
    "lab":          {"temperature": (20, 30), "occupancy": (0, 50),  "energy": (100, 500)},
    "office":       {"temperature": (22, 28), "occupancy": (0, 15),  "energy": (20, 150)},
    "canteen":      {"temperature": (24, 34), "occupancy": (0, 200), "energy": (100, 400)},
    "auditorium":   {"temperature": (22, 32), "occupancy": (0, 1000),"energy": (200, 500)},
    "hostel":       {"temperature": (24, 32), "occupancy": (0, 500), "energy": (50, 300)},
    "outdoor":      {"occupancy":   (0, 700)},
    "library":      {"temperature": (22, 28), "occupancy": (0, 400), "energy": (50, 250)},
    "server_room":  {"temperature": (18, 24), "energy":      (200, 500)},
}


def generate_seed_sensors():
    topology = CampusTopology()
    sensors = []

    for room in topology.all_rooms():
        rt = ROOM_TYPE_DEFAULTS.get(room.room_type, {})
        for st in room.sensors:
            cfg = dict(TYPE_CONFIGS.get(st, TYPE_CONFIGS["temperature"]))
            if st in rt:
                cfg["min_value"] = rt[st][0]
                cfg["max_value"] = rt[st][1]
            sensor = {
                "id": f"{room.room_id}-{st}",
                "name": f"{room.room_id} {st}",
                "building_id": room.building_id,
                "floor": room.floor,
                "room_id": room.room_id,
                "sensor_type": st,
                "enabled": True,
                "behavior_mode": "normal",
                "config": cfg,
            }
            sensors.append(sensor)
    return sensors


if __name__ == "__main__":
    import json
    seeds = generate_seed_sensors()
    print(json.dumps(seeds, indent=2))
    print(f"\nTotal: {len(seeds)} sensors", file=sys.stderr)
