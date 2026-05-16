"""
Zone-based sensor package for University of Moratuwa Smart Campus.

Each zone type (classroom, canteen, library, etc.) has its own module
with zone-specific occupancy logic that inherits from base sensors.

This makes it easy to change simulation strategy per zone independently.
"""

from .auditorium import AuditoriumZone
from .base_zone import BaseZone, ZoneContext
from .canteen import CanteenZone
from .classroom import ClassroomZone
from .hostel import HostelZone
from .library import LibraryZone
from .office import OfficeZone
from .outdoor import OutdoorZone
from .server_room import ServerRoomZone

__all__ = [
    "BaseZone",
    "ZoneContext",
    "ClassroomZone",
    "CanteenZone",
    "LibraryZone",
    "HostelZone",
    "OutdoorZone",
    "AuditoriumZone",
    "OfficeZone",
    "ServerRoomZone",
    "get_zone_for_room_type",
]

# Zone registry mapping room_type -> Zone class
_ZONE_REGISTRY = {
    "classroom": ClassroomZone,
    "lab": ClassroomZone,  # Labs use same occupancy pattern as classrooms
    "canteen": CanteenZone,
    "library": LibraryZone,
    "hostel": HostelZone,
    "outdoor": OutdoorZone,
    "auditorium": AuditoriumZone,
    "office": OfficeZone,
    "server_room": ServerRoomZone,
}


def get_zone_for_room_type(room_type: str) -> type[BaseZone]:
    """Return the appropriate Zone class for a given room_type string."""
    zone_class = _ZONE_REGISTRY.get(room_type)
    if zone_class is None:
        raise ValueError(f"Unknown room_type: {room_type}. Available: {list(_ZONE_REGISTRY.keys())}")
    return zone_class
