"""
Server room zone.

Key patterns:
  - No human occupancy (equipment only)
  - Temperature sensor: precision cooling 20-22°C
  - Energy sensor: constant high draw from servers
  - No occupancy sensor (server rooms don't have people)
"""

from .base_zone import BaseZone, ZoneContext


class ServerRoomZone(BaseZone):
    """
    Server room zone - no human occupancy, equipment monitoring only.
    """

    def _target_ratio(self, ctx: ZoneContext) -> float:
        """Always 0 - server rooms have no human occupancy."""
        return 0.0

    def _create_sensors(self) -> None:
        """
        Override to only create temperature and energy sensors.
        Server rooms don't need occupancy sensors.
        """
        from simulator.sensors.energy import EnergySensor
        from simulator.sensors.temperature import TemperatureSensor

        for sensor_type in self.room.sensors:
            kwargs = dict(
                sensor_id=f"{self.room_id}-{sensor_type}",
                room_id=self.room_id,
                building_id=self.building_id,
                floor=self.floor,
                sensor_type=sensor_type,
                room_type=self.room_type,
            )

            if sensor_type == "temperature":
                sensor = TemperatureSensor(**kwargs)
            elif sensor_type == "energy":
                sensor = EnergySensor(**kwargs)
            else:
                # Skip occupancy and other sensors for server rooms
                continue

            self._sensors.append(sensor)
