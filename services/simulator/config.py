import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class SimulatorConfig:
    mqtt_host:       str   = os.getenv("MQTT_HOST", "mosquitto")
    mqtt_port:       int   = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_keepalive:  int   = int(os.getenv("MQTT_KEEPALIVE", "60"))
    publish_interval_s: float = float(os.getenv("PUBLISH_INTERVAL_S", "5.0"))
    log_level:       str   = os.getenv("LOG_LEVEL", "INFO")
    campus_timezone: str   = os.getenv("CAMPUS_TIMEZONE", "Asia/Colombo")
    mqtt_username:   str   = os.getenv("MQTT_USERNAME", "")
    mqtt_password:   str   = os.getenv("MQTT_PASSWORD", "")


config = SimulatorConfig()
