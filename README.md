# llm-load-test-exporter

### Overview
The purpose of this program is to run [llm-load-test](https://github.com/openshift-psap/llm-load-test) application and then serve the resulting metrics to a /metrics endpoint. This is meant to be run in a kubernetes/openshift environment.

This application is split into 2:
1. run-llm-load-test: This is the application that actually runs llm-load-test against all models running in a cluster, and saves the output into a volume.
2. exporter: This application exports the results of running llm-load-test to the /metrics endpoint. 

### Deploying Application in OpenShift

In order to deploy this application in OpenShift do the following:

1. Modify the namespace this will be deployed to in base/kustomization.yaml
2. Modify how often the load test is run by modifying WAIT_TIME env variable in base/deployment.yaml
3. Run `oc create -k base/`

### Example output when querying the /metrics endpoint:

```
# HELP llm_performance_itl Inter-token Latency (ms)
# TYPE llm_performance_itl gauge
llm_performance_itl{model="granite-internal",namespace="granite-instruct"} 15.718567660626242
llm_performance_itl{model="granite-test2",namespace="granite-instruct"} 15.71746298495461
llm_performance_itl{model="granite",namespace="granite-instruct"} 15.718144651721506
# HELP llm_performance_ttft Time to First Token (ms)
# TYPE llm_performance_ttft gauge
# HELP llm_performance_response_time Response Time (ms)
# TYPE llm_performance_response_time gauge
llm_performance_response_time{model="granite-internal",namespace="granite-instruct"} 7538.3247534434
llm_performance_response_time{model="granite-test2",namespace="granite-instruct"} 7540.998776753743
llm_performance_response_time{model="granite",namespace="granite-instruct"} 7524.742523829143
# HELP llm_performance_throughput Throughput (requests/sec)
# TYPE llm_performance_throughput gauge
llm_performance_throughput{model="granite-internal",namespace="granite-instruct"} 18.800226791575348
llm_performance_throughput{model="granite-test2",namespace="granite-instruct"} 18.756188413911982
llm_performance_throughput{model="granite",namespace="granite-instruct"} 18.804055740773666
# HELP llm_performance_latency Latency (ms)
# TYPE llm_performance_latency gauge
llm_performance_latency{model="granite-internal",namespace="granite-instruct"} 277.4471044540405
llm_performance_latency{model="granite-test2",namespace="granite-instruct"} 285.0987911224365
llm_performance_latency{model="granite",namespace="granite-instruct"} 268.87357234954834
```