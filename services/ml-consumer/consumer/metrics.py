"""
Prometheus metrics for the ML consumer.
Exposes counters on :9091/metrics.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from aiohttp import web

logger = logging.getLogger("ml-consumer.metrics")


class ConsumerMetrics:
    def __init__(self) -> None:
        self.processed: dict[str, int] = defaultdict(int)
        self.anomalies: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)

    def record_processed(self, topic: str) -> None:
        self.processed[topic] += 1

    def record_anomaly(self, topic: str) -> None:
        self.anomalies[topic] += 1

    def record_error(self, topic: str) -> None:
        self.errors[topic] += 1

    def render(self) -> str:
        lines = ["# HELP campus_consumer_processed_total Messages processed"]
        lines.append("# TYPE campus_consumer_processed_total counter")
        for topic, count in self.processed.items():
            safe = topic.replace(".", "_").replace("-", "_")
            lines.append(f'campus_consumer_processed_total{{topic="{safe}"}} {count}')

        lines.append("# HELP campus_consumer_anomalies_total Anomalies detected")
        lines.append("# TYPE campus_consumer_anomalies_total counter")
        for topic, count in self.anomalies.items():
            safe = topic.replace(".", "_").replace("-", "_")
            lines.append(f'campus_consumer_anomalies_total{{topic="{safe}"}} {count}')

        lines.append("# HELP campus_consumer_errors_total Processing errors")
        lines.append("# TYPE campus_consumer_errors_total counter")
        for topic, count in self.errors.items():
            safe = topic.replace(".", "_").replace("-", "_")
            lines.append(f'campus_consumer_errors_total{{topic="{safe}"}} {count}')

        return "\n".join(lines) + "\n"


# Singleton metrics (shared across imports)
_metrics = ConsumerMetrics()


async def _handle_metrics(request: web.Request) -> web.Response:
    return web.Response(text=_metrics.render(), content_type="text/plain")


async def serve_metrics(port: int = 9091) -> None:
    """Serve Prometheus /metrics endpoint."""
    app = web.Application()
    app.router.add_get("/metrics", _handle_metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Metrics server started on :{port}/metrics")
