# llm-load-test-exporter

Prometheus metrics exporter for [llm-load-test](https://github.com/openshift-psap/llm-load-test). Automatically discovers KServe InferenceService models in a Kubernetes/OpenShift cluster, runs load tests against them, and exports the results as Prometheus metrics.

## Architecture

The application runs as a Kubernetes Deployment with two containers sharing an `emptyDir` volume:

| Container | Purpose |
|-----------|---------|
| **runner** | Discovers models via the Kubernetes API, runs `llm-load-test` against each, writes JSON results to the shared volume |
| **exporter** | Reads the JSON results and serves Prometheus metrics on `/metrics` (port 8080) |

`llm-load-test` is installed as a **pip dependency** from the [upstream repository](https://github.com/openshift-psap/llm-load-test) — no vendored copy.

## Metrics Exposed

| Metric | Description |
|--------|-------------|
| `llm_load_test_tpot_mean_ms` | Mean Time Per Output Token (ms) |
| `llm_load_test_ttft_mean_ms` | Mean Time to First Token (ms) |
| `llm_load_test_itl_mean_ms` | Mean Inter-Token Latency (ms) |
| `llm_load_test_response_time_mean_ms` | Mean Response Time (ms) |
| `llm_load_test_tpot_p95_ms` | P95 Time Per Output Token (ms) |
| `llm_load_test_ttft_p95_ms` | P95 Time to First Token (ms) |
| `llm_load_test_response_time_p95_ms` | P95 Response Time (ms) |
| `llm_load_test_throughput_tokens_per_sec` | Throughput (tokens/sec) |
| `llm_load_test_total_requests` | Total requests in the load test run |
| `llm_load_test_failure_rate_percent` | Percentage of failed requests |

All metrics carry `model` and `namespace` labels.

## Prerequisites

- An OpenShift/Kubernetes cluster with KServe InferenceService models deployed
- Models must have the label `gather_llm_metrics: "true"` on their pods to opt in to load testing
- A ServiceAccount with permissions to list pods and read secrets across namespaces

## Deploying to OpenShift

1. Set the target namespace in `base/kustomization.yaml`
2. Adjust environment variables in `base/deployment.yaml` as needed:
   - `WAIT_TIME` — seconds between load test runs (default: `120`)
   - `CONCURRENCY` — number of concurrent users (default: `8`)
   - `DURATION` — duration of each load test in seconds (default: `30`)
   - `STREAMING` — use streaming API (default: `true`)
   - `ENDPOINT` — OpenAI-compatible endpoint path (default: `/v1/chat/completions`)
3. Deploy:

```bash
oc apply -k base/
```

## Building Container Images

```bash
# Exporter
podman build -f exporter/Containerfile -t quay.io/rh-ee-istaplet/nerc-tools:llm-load-test-exporter exporter/

# Runner
podman build -f runner/Containerfile -t quay.io/rh-ee-istaplet/nerc-tools:llm-load-test-runner runner/
```

## Notes

**Exporter logs:** You may see `[ERROR] Control server error: [Errno 13] Permission denied` from Gunicorn at startup. **This has no effect on the application** — metrics are served and scraped as usual. The error occurs when the container cannot create Gunicorn's control socket (e.g. under a read-only root filesystem). It is safe to ignore.

## Project Structure

```
llm-load-test-exporter/
├── base/                  # Kubernetes/OpenShift manifests (Kustomize)
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── serviceaccount.yaml
│   ├── clusterrole.yaml
│   ├── clusterrolebinding.yaml
│   ├── servicemonitor.yaml
│   ├── files/
│   │   └── uwl_metrics_list.yaml
│   └── kustomization.yaml
├── exporter/              # Prometheus metrics exporter (Flask + gunicorn)
│   ├── Containerfile
│   ├── exporter.py
│   ├── wsgi.py
│   └── requirements.txt
├── runner/                # Load test runner
│   ├── Containerfile
│   ├── runner.py
│   ├── requirements.txt
│   └── datasets/          # Default dataset for load tests
│       └── dataset.jsonl
└── README.md
```

## Example /metrics Output

```
# HELP llm_load_test_tpot_mean_ms Mean Time Per Output Token (ms)
# TYPE llm_load_test_tpot_mean_ms gauge
llm_load_test_tpot_mean_ms{model="granite",namespace="granite-instruct"} 15.718
# HELP llm_load_test_ttft_mean_ms Mean Time to First Token (ms)
# TYPE llm_load_test_ttft_mean_ms gauge
llm_load_test_ttft_mean_ms{model="granite",namespace="granite-instruct"} 268.87
# HELP llm_load_test_throughput_tokens_per_sec Throughput (tokens/sec)
# TYPE llm_load_test_throughput_tokens_per_sec gauge
llm_load_test_throughput_tokens_per_sec{model="granite",namespace="granite-instruct"} 18.804
# HELP llm_load_test_failure_rate_percent Percentage of failed requests
# TYPE llm_load_test_failure_rate_percent gauge
llm_load_test_failure_rate_percent{model="granite",namespace="granite-instruct"} 0.0
```
