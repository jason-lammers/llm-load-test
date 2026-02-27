"""
Prometheus metrics exporter for llm-load-test results.

Reads JSON output files produced by the runner container and exposes
them as Prometheus gauge metrics on the /metrics endpoint.
"""

import json
import logging
import os

from flask import Flask
from prometheus_client import CollectorRegistry, Gauge, generate_latest

LOG = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/shared_data/output")

# ---------------------------------------------------------------------------
# Prometheus metrics registry
# ---------------------------------------------------------------------------

registry = CollectorRegistry()

LABEL_NAMES = ["model", "namespace"]

# Per-request timing metrics (mean values)
tpot_metric = Gauge(
    "llm_load_test_tpot_mean_ms",
    "Mean Time Per Output Token (ms)",
    labelnames=LABEL_NAMES,
    registry=registry,
)
ttft_metric = Gauge(
    "llm_load_test_ttft_mean_ms",
    "Mean Time to First Token (ms)",
    labelnames=LABEL_NAMES,
    registry=registry,
)
itl_metric = Gauge(
    "llm_load_test_itl_mean_ms",
    "Mean Inter-Token Latency (ms)",
    labelnames=LABEL_NAMES,
    registry=registry,
)
response_time_metric = Gauge(
    "llm_load_test_response_time_mean_ms",
    "Mean Response Time (ms)",
    labelnames=LABEL_NAMES,
    registry=registry,
)

# Percentile metrics
tpot_p95_metric = Gauge(
    "llm_load_test_tpot_p95_ms",
    "P95 Time Per Output Token (ms)",
    labelnames=LABEL_NAMES,
    registry=registry,
)
ttft_p95_metric = Gauge(
    "llm_load_test_ttft_p95_ms",
    "P95 Time to First Token (ms)",
    labelnames=LABEL_NAMES,
    registry=registry,
)
response_time_p95_metric = Gauge(
    "llm_load_test_response_time_p95_ms",
    "P95 Response Time (ms)",
    labelnames=LABEL_NAMES,
    registry=registry,
)

# Throughput and request counts
throughput_metric = Gauge(
    "llm_load_test_throughput_tokens_per_sec",
    "Throughput (tokens/sec)",
    labelnames=LABEL_NAMES,
    registry=registry,
)
total_requests_metric = Gauge(
    "llm_load_test_total_requests",
    "Total requests in the load test run",
    labelnames=LABEL_NAMES,
    registry=registry,
)
failure_rate_metric = Gauge(
    "llm_load_test_failure_rate_percent",
    "Percentage of failed requests",
    labelnames=LABEL_NAMES,
    registry=registry,
)

ALL_GAUGES = [
    tpot_metric,
    ttft_metric,
    itl_metric,
    response_time_metric,
    tpot_p95_metric,
    ttft_p95_metric,
    response_time_p95_metric,
    throughput_metric,
    total_requests_metric,
    failure_rate_metric,
]


def _safe_get(data: dict, *keys, default=None):
    """Safely traverse nested dicts."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _set_gauge(gauge: Gauge, labels: dict, value) -> None:
    """Set a gauge only if value is not None."""
    if value is not None:
        gauge.labels(**labels).set(value)


def set_metrics() -> None:
    """Read output JSON files and update Prometheus gauges."""
    # Clear all previous metric values
    for gauge in ALL_GAUGES:
        gauge._metrics.clear()

    if not os.path.isdir(OUTPUT_DIR):
        LOG.warning("Output directory does not exist: %s", OUTPUT_DIR)
        return

    files = os.listdir(OUTPUT_DIR)
    if not files:
        LOG.info("No output files found in %s", OUTPUT_DIR)
        return

    for filename in files:
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(OUTPUT_DIR, filename)

        # Parse model name and namespace from filename: {model}_{namespace}.json
        base = os.path.splitext(filename)[0]
        parts = base.rsplit("_", 1)
        if len(parts) != 2:
            LOG.warning("Skipping file with unexpected name format: %s", filename)
            continue

        model_name, namespace = parts
        labels = {"model": model_name, "namespace": namespace}

        try:
            with open(filepath, "r") as f:
                results = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            LOG.error("Failed to read %s: %s", filepath, exc)
            continue

        summary = results.get("summary", {})
        if not summary:
            LOG.warning("No summary in %s", filepath)
            continue

        # Mean metrics
        _set_gauge(tpot_metric, labels, _safe_get(summary, "tpot", "mean"))
        _set_gauge(ttft_metric, labels, _safe_get(summary, "ttft", "mean"))
        _set_gauge(itl_metric, labels, _safe_get(summary, "itl", "mean"))
        _set_gauge(response_time_metric, labels,
                   _safe_get(summary, "response_time", "mean"))

        # P95 metrics
        _set_gauge(tpot_p95_metric, labels,
                   _safe_get(summary, "tpot", "percentile_95"))
        _set_gauge(ttft_p95_metric, labels,
                   _safe_get(summary, "ttft", "percentile_95"))
        _set_gauge(response_time_p95_metric, labels,
                   _safe_get(summary, "response_time", "percentile_95"))

        # Throughput and request counts
        _set_gauge(throughput_metric, labels, summary.get("throughput"))
        _set_gauge(total_requests_metric, labels,
                   summary.get("total_requests"))
        _set_gauge(failure_rate_metric, labels, summary.get("failure_rate"))

        LOG.info("Updated metrics for model=%s namespace=%s",
                 model_name, namespace)


def create_app(**kwargs) -> Flask:
    """Create the Flask application."""
    app = Flask(__name__)

    @app.route("/metrics", methods=["GET"])
    def export_metrics():
        set_metrics()
        return (
            generate_latest(registry),
            200,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return "ok", 200

    @app.route("/readyz", methods=["GET"])
    def readyz():
        return "ok", 200

    return app
