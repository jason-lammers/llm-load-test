from flask import Flask, request, jsonify
import subprocess
from prometheus_client import Gauge, generate_latest, CollectorRegistry
import os
import json
import yaml
from kubernetes import config, client
import logging


metrics = Flask(__name__)
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
    config.load_kube_config()
except config.ConfigException as e:
    LOG.error("Could not configure Kubernetes client: %s", str(e))
    exit(1)

v1 = client.CoreV1Api()


# Configure llm-load-test config.yaml
def set_config(model_name, host_url, namespace):
    config_path = "./llm-load-test/config.yaml"

    with open(config_path, "r") as file:
        try:
            config = yaml.safe_load(file)
        except Exception as e:
            print(f"Error loading config.yaml file: {e}")
            return

    config["plugin_options"]["model_name"] = model_name
    config["plugin_options"]["host"] = host_url
    config["output"]["file"] = f"{model_name}_{namespace}.json"

    with open(config_path, "w") as file:
        try:
            config = yaml.dump(config, file)
        except Exception as e:
            print(f"Error writing config.yaml file: {e}")
            return


# Run llm-load-test and gather metrics for each model
def gather_metrics():
    # Gather model information for the config.yaml
    model_pods = v1.list_pod_for_all_namespaces(
        label_selector="serving.kserve.io/inferenceservice"
    )

    for pod in model_pods.items:
        model_name = pod.metadata.labels["serving.kserve.io/inferenceservice"]
        namespace = pod.metadata.namespace
        host_url = f"https://{model_name}-{namespace}.apps.albany.nerc.mghpcc.org"

        set_config(model_name, host_url, namespace)

        llm_load_test()

        print(f"Completed load test for model: {model_name} in {namespace} namespace")

# Run llm-load-test
def llm_load_test():
    try:
        subprocess.run(["python", "load_test.py"], check=True, cwd="llm-load-test")
    except Exception as e:
        return f"Error running load_test.py: {e}"


if __name__ == "__main__":
    gather_metrics()
