"""
Runner that discovers models in a Kubernetes/OpenShift cluster,
runs llm-load-test against each, and writes output JSON files
for the exporter to serve as Prometheus metrics.
"""

import base64
import logging
import os
import subprocess
import sys
import tempfile
import time

import yaml
from kubernetes import client, config

LOG = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# Kubernetes setup
# ---------------------------------------------------------------------------

try:
    config.load_incluster_config()
except config.ConfigException:
    try:
        config.load_kube_config()
    except config.ConfigException as exc:
        LOG.error("Could not configure Kubernetes client: %s", exc)
        sys.exit(1)

v1 = client.CoreV1Api()

# ---------------------------------------------------------------------------
# Constants / env-driven config
# ---------------------------------------------------------------------------

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/shared_data/output")
DATASET_PATH = os.environ.get("DATASET_PATH", "/app/datasets/dataset.jsonl")
WAIT_TIME = int(os.environ.get("WAIT_TIME", "120"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "8"))
DURATION = int(os.environ.get("DURATION", "30"))
STREAMING = os.environ.get("STREAMING", "true").lower() == "true"
ENDPOINT = os.environ.get("ENDPOINT", "/v1/chat/completions")
LOG_LEVEL = os.environ.get("LLM_LOAD_TEST_LOG_LEVEL", "info")


def build_config(model_name: str, host_url: str, namespace: str,
                 auth_token: str | None = None) -> dict:
    """Build a llm-load-test config dict for a single model."""
    cfg = {
        "plugin": "openai_plugin",
        "plugin_options": {
            "host": host_url,
            "model_name": model_name,
            "streaming": STREAMING,
            "endpoint": ENDPOINT,
        },
        "load_options": {
            "type": "constant",
            "concurrency": CONCURRENCY,
            "duration": DURATION,
        },
        "dataset": {
            "file": DATASET_PATH,
        },
        "output": {
            "dir": OUTPUT_DIR,
            "file": f"{model_name}_{namespace}.json",
        },
    }

    if auth_token:
        cfg["plugin_options"]["authorization"] = auth_token

    return cfg


def get_auth_token(model_name: str, namespace: str) -> str | None:
    """Retrieve the bearer token from a KServe service-account secret."""
    try:
        secret = v1.read_namespaced_secret(
            f"default-name-{model_name}-sa", namespace
        )
        return base64.b64decode(secret.data["token"]).decode("utf-8")
    except Exception as exc:
        LOG.warning("Could not read auth secret for %s/%s: %s",
                    namespace, model_name, exc)
        return None


def run_load_test(cfg: dict) -> None:
    """Write a temporary config and invoke the ``load-test`` CLI."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as tmp:
        yaml.dump(cfg, tmp)
        config_path = tmp.name

    try:
        result = subprocess.run(
            ["load-test", "-c", config_path, "-log", LOG_LEVEL],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        if result.returncode != 0:
            LOG.error(
                "load-test failed (rc=%d) for %s:\nstdout: %s\nstderr: %s",
                result.returncode,
                cfg["plugin_options"]["model_name"],
                result.stdout[-500:] if result.stdout else "",
                result.stderr[-500:] if result.stderr else "",
            )
        else:
            LOG.info("load-test completed successfully for %s",
                     cfg["plugin_options"]["model_name"])
    except subprocess.TimeoutExpired:
        LOG.error("load-test timed out for %s",
                  cfg["plugin_options"]["model_name"])
    except FileNotFoundError:
        LOG.error(
            "load-test CLI not found. Make sure llm-load-test is installed."
        )
        sys.exit(1)
    finally:
        os.unlink(config_path)


def discover_and_test_models() -> None:
    """Discover KServe InferenceService models and run load tests."""
    try:
        model_pods = v1.list_pod_for_all_namespaces(
            label_selector="serving.kserve.io/inferenceservice"
        )
    except Exception as exc:
        LOG.error("Failed to list model pods: %s", exc)
        return

    for pod in model_pods.items:
        model_name = pod.metadata.labels.get(
            "serving.kserve.io/inferenceservice", "unknown"
        )
        namespace = pod.metadata.namespace

        # Only test pods that are Running and opted-in
        gather = pod.metadata.labels.get("gather_llm_metrics")
        if pod.status.phase != "Running" or not gather:
            LOG.debug(
                "Skipping %s/%s (phase=%s, gather_llm_metrics=%s)",
                namespace, model_name, pod.status.phase, gather,
            )
            continue

        # Check if token auth is required
        annotations = pod.metadata.annotations or {}
        enable_auth = (
            annotations.get("security.opendatahub.io/enable-auth") == "true"
        )
        auth_token = get_auth_token(model_name, namespace) if enable_auth else None

        host_url = f"https://{model_name}.{namespace}.svc.cluster.local"

        LOG.info("Running load test for model %s in namespace %s",
                 model_name, namespace)

        cfg = build_config(model_name, host_url, namespace, auth_token)
        run_load_test(cfg)

        LOG.info("Completed load test for model %s in namespace %s",
                 model_name, namespace)


def main() -> None:
    """Main loop: discover models and run load tests periodically."""
    LOG.info(
        "Starting runner (wait=%ds, concurrency=%d, duration=%ds)",
        WAIT_TIME, CONCURRENCY, DURATION,
    )

    while True:
        discover_and_test_models()
        LOG.info("Sleeping %d seconds until next run...", WAIT_TIME)
        time.sleep(WAIT_TIME)


if __name__ == "__main__":
    main()

