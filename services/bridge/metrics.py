"""
In-process counters for the bridge.

Exposed at /metrics (plain text) by a lightweight HTTP server so the bridge
can be monitored without a full Prometheus setup.  Import and increment from
anywhere in the bridge codebase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BridgeMetrics:
    received:      int = 0   # total MQTT messages received
    valid:         int = 0   # successfully validated and forwarded to Kafka
    invalid:       int = 0   # validation failures → DLQ
    dlq_errors:    int = 0   # failed to write to DLQ itself
    kafka_errors:  int = 0   # Kafka send failures

    # Per-sensor-type counts
    by_type: dict[str, int] = field(default_factory=dict)

    def record(self, sensor_type: str, *, valid: bool) -> None:
        self.received += 1
        if valid:
            self.valid += 1
            self.by_type[sensor_type] = self.by_type.get(sensor_type, 0) + 1
        else:
            self.invalid += 1

    def to_text(self) -> str:
        lines = [
            f"bridge_messages_received_total {self.received}",
            f"bridge_messages_valid_total {self.valid}",
            f"bridge_messages_invalid_total {self.invalid}",
            f"bridge_dlq_errors_total {self.dlq_errors}",
            f"bridge_kafka_errors_total {self.kafka_errors}",
        ]
        for stype, count in self.by_type.items():
            lines.append(f'bridge_messages_by_type_total{{type="{stype}"}} {count}')
        return "\n".join(lines) + "\n"


# Module-level singleton — import and use directly
metrics = BridgeMetrics()


async def serve_metrics(host: str = "0.0.0.0", port: int = 9090) -> None:
    """Minimal HTTP server exposing /metrics as Prometheus text format."""
    from aiohttp import web

    async def handler(request: web.Request) -> web.Response:
        return web.Response(text=metrics.to_text(), content_type="text/plain")

    app = web.Application()
    app.router.add_get("/metrics", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"Metrics endpoint: http://{host}:{port}/metrics")
