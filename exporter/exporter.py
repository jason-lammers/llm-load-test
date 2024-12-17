from flask import Flask
from prometheus_client import Gauge, generate_latest, CollectorRegistry
import os
import json
from kubernetes import config, client
import logging


registry = CollectorRegistry()

itl_metric = Gauge(
    "itl",
    "Inter-token Latency (ms)",
    labelnames=["model", "namespace"],
    registry=registry,
)
ttft_metric = Gauge(
    "ttft",
    "Time to First Token (ms)",
    labelnames=["model", "namespace"],
    registry=registry,
)
response_time_metric = Gauge(
    "response_time",
    "Response Time (ms)",
    labelnames=["model", "namespace"],
    registry=registry,
)
throughput_metric = Gauge(
    "throughput",
    "Throughput (requests/sec)",
    labelnames=["model", "namespace"],
    registry=registry,
)

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    config.load_incluster_config()
except config.ConfigException as e:
    LOG.error("Could not configure Kubernetes client: %s", str(e))
    exit(1)

v1 = client.CoreV1Api()


# Read from output files and set metrics
def set_metrics():
    output_directory = "/shared_data/llm-load-test/output/"

    output_directory_encoded = os.fsencode("/shared_data/llm-load-test/output/")

    # Loop through files in output directory
    output_files = os.listdir(output_directory_encoded)

    for file in output_files:
        filename = os.fsdecode(file)
        filename_split = filename.split("_")

        model_name = filename_split[0]
        namespace = os.path.splitext(filename_split[1])[0]

        with open(f"{output_directory}/{filename}", "r") as f:
            results = json.load(f)

            summary = results.get("summary", {})
            if summary:
                itl_metric.labels(model=model_name, namespace=namespace).set(
                    summary["itl"]["mean"]
                )
                ttft_metric.labels(model=model_name, namespace=namespace).set(
                    summary["ttft"]["mean"]
                )
                response_time_metric.labels(model=model_name, namespace=namespace).set(
                    summary["response_time"]["mean"]
                )
                throughput_metric.labels(model=model_name, namespace=namespace).set(
                    summary["throughput"]
                )

        print(f"Uploaded metrics for model: {model_name}")


def create_app(**config):
    app = Flask(__name__)

    @app.route("/metrics", methods=["GET"])
    def export_metrics():
        set_metrics()

        return (
            generate_latest(registry),
            200,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    return app
