from flask import Flask, request, jsonify
from prometheus_client import start_http_server, Summary
import subprocess
from prometheus_client import Gauge, generate_latest, CollectorRegistry
import os
import json


metrics = Flask(__name__)

registry = CollectorRegistry()

itl_metric = Gauge("itl", "Inter-token Latency (ms)", registry=registry)
ttft_metric = Gauge("ttft", "Time to First Token (ms)", registry=registry)
response_time_metric = Gauge("response_time", "Response Time (ms)", registry=registry)
throughput_metric = Gauge("throughput", "Throughput (requests/sec)", registry=registry)


def llm_load_test():
    try:
        subprocess.run(["python", "load_test.py"], check=True, cwd="llm-load-test")
    except Exception as e:
        return "Error running load_test.py"


@metrics.route("/metrics", methods=["GET"])
def export_metrics():
    llm_load_test()

    output_file = "./llm-load-test/output/output-001.json"

    if os.path.exists(output_file):
        with open(output_file, "r") as f:
            results = json.load(f)

        summary = results.get("summary", {})
        if summary:
            itl_metric.set(summary["itl"]["mean"])
            ttft_metric.set(summary["ttft"]["mean"])
            response_time_metric.set(summary["response_time"]["mean"])
            throughput_metric.set(summary["throughput"])
        return (
            generate_latest(registry),
            200,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


if __name__ == "__main__":
    metrics.run(host="0.0.0.0", port=8443)
