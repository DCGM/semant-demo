# Observability

This document is the developer handover for telemetry in semANT. It describes what the application emits today, how a deployment is identified, and how to extend the implementation without leaking user data or creating unbounded metric cardinality.

## Contents

- [Architecture and ownership](#architecture-and-ownership)
- [Deployment identity and environments](#deployment-identity-and-environments)
- [What is implemented](#what-is-implemented)
- [Runtime configuration](#runtime-configuration)
- [Application logs in Grafana](#application-logs-in-grafana)
- [Traces and metrics](#traces-and-metrics)
- [Extending telemetry](#extending-telemetry) — add a metric, trace/span, or structured log
  - [Add a metric](#add-a-metric)
  - [Add a trace/span](#add-a-tracespan)
  - [Add a log field](#add-a-log-field)
  
## Architecture and ownership

```text
FastAPI backend
  └─ semant_demo/opentelemetry.py
       ├─ OTLP/HTTP exporters (logs, traces, metrics)
       ├─ resource attributes: service, environment, instance
       ├─ FastAPI and system instrumentation
       └─ custom feature metrics
             │
             └─ OTLP Collector / LGTM receiver (:4318)
                  ├─ logs    → Loki
                  ├─ traces  → Tempo
                  └─ metrics → Prometheus-compatible store
                                      └─ Grafana Explore and dashboards
```

`semant_demo_backend/semant_demo/opentelemetry.py` owns providers, exporters and instrumentation. It is the only module that should create an OpenTelemetry provider or exporter. `semant_demo_backend/semant_demo/main.py` creates telemetry once during application import, records the completed feature action in the HTTP middleware, instruments the FastAPI application after routes are registered, and flushes telemetry during shutdown.

The Collector and LGTM storage are infrastructure outside this repository. Code can successfully send OTLP to port 4318 while data is still absent from Grafana if the Collector does not have the corresponding `logs`, `traces`, or `metrics` pipeline enabled.

## Deployment identity and environments

Every signal carries these OpenTelemetry resource attributes. In Loki/Prometheus they are normally normalized to underscore labels.

| Attribute | Grafana/Prometheus label | Meaning and rule |
|---|---|---|
| `service.name` | `service_name` | Logical application name. Keep it as `semant-demo-app` for every semANT backend deployment. It separates this project from other projects sharing LGTM. |
| `deployment.environment.name` | `deployment_environment_name` | Logical deployed version/environment; use it to select one deployment in a dashboard. |
| `service.instance.id` | `service_instance_id` | Host/container identity. It changes after a redeploy and is for diagnosis, not normally for dashboard grouping. |

CI writes `DEPLOYMENT_ENVIRONMENT` for each deploy:

| Deployment | Environment value | Intended use |
|---|---|---|
| production release | `production` | Real public deployment |
| branch `main` test deploy | `test-main` | Persistent integration/testing deployment |
| pull request number `123` | `test-pr-123` | Temporary preview deployment for that pull request |

Do not use a raw branch name, commit SHA, user name, URL, or random identifier as an environment value. Use `service_name="semant-demo-app"` and `deployment_environment_name` to identify the source deployment in shared dashboard queries.

## What is implemented

| Signal | Source in code | Current content | Intended destination |
|---|---|---|---|
| Logs | HTTP middleware in `main.py` and ordinary Python `logging` | Completed request log, request ID, method, path, status, duration; active trace/span IDs are injected automatically | Loki |
| Traces | `FastAPIInstrumentor` in `opentelemetry.py` | Server span for each FastAPI request | Tempo |
| Automatic metrics | FastAPI and `SystemMetricsInstrumentor` | Standard HTTP metrics plus process CPU time/utilization, memory usage and thread count | Prometheus-compatible metrics store |
| Feature request counter | `record_feature_request()` | Completed RAG, search, summarization, AI-assistance and tagging actions; labels `feature`, `authentication`, `outcome` | Prometheus-compatible metrics store |
| Feature duration histogram | `record_feature_request()` | Duration of those same completed user actions, with the same labels; supports p50/p95/p99 | Prometheus-compatible metrics store |

The feature metrics deliberately exclude `GET` endpoints, `/health`, static assets, and unclassified routes. `authentication="bearer_token"` means only that a request included a Bearer token; it is not a count of unique users and no user or token value is exported.

Prometheus names of the custom feature metrics:

```text
semant_demo_feature_requests_total
semant_demo_feature_request_duration_seconds_bucket
semant_demo_feature_request_duration_seconds_sum
semant_demo_feature_request_duration_seconds_count
```

## Runtime configuration

`Config` in `semant_demo_backend/semant_demo/config.py` reads these variables. Local development defaults to telemetry disabled so tests and local runs do not try to contact infrastructure.

| Variable | Purpose |
|---|---|
| `OTEL_ENABLED` | Enables all three signals. CI sets it to `true` for production, `test-main`, and PR previews. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector base URL; deployed containers use `http://lgtm:4318`. |
| `OTEL_EXPORTER_OTLP_LOGS_PATH`, `OTEL_EXPORTER_OTLP_TRACES_PATH`, `OTEL_EXPORTER_OTLP_METRICS_PATH` | OTLP/HTTP paths, normally `/v1/logs`, `/v1/traces`, `/v1/metrics`. |
| `OTEL_METRIC_EXPORT_INTERVAL_MS` | Metric export period; production template uses `10000` ms. |
| `OTEL_SERVICE_NAME` | `service.name`; deployed value is `semant-demo-app`. |
| `DEPLOYMENT_ENVIRONMENT` | `deployment.environment.name`; set by CI as described above. |

The deployment templates set these values and the CI workflow rewrites `OTEL_ENABLED` and `DEPLOYMENT_ENVIRONMENT` for each deployment. Do not hard-code a deployment environment in Python.

## Application logs in Grafana

The backend sends standard Python `logging` records to the OpenTelemetry Collector over OTLP/HTTP. The collector is expected to route them to Loki.

Both committed `.env` templates enable telemetry. CI also sets it explicitly for every deployment type:

| Deployment | `OTEL_ENABLED` | `deployment.environment.name` |
|---|---:|---|
| production release | `true` | `production` |
| `main` test deployment | `true` | `test-main` |
| pull request | `true` | `test-pr-<number>` |

The resulting production configuration is:

```dotenv
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://lgtm:4318
OTEL_EXPORTER_OTLP_LOGS_PATH=/v1/logs
OTEL_SERVICE_NAME=semant-demo-app
DEPLOYMENT_ENVIRONMENT=production
```

The hostname `lgtm` works because both containers are attached to the external Docker network `web`. When the backend runs directly on the SemAnT PC rather than in Docker, use `http://localhost:4318` instead and explicitly set `OTEL_ENABLED=true` for that run.

Every HTTP request produces one structured log with these attributes:

- `request.id`: incoming `X-Request-ID` or a newly generated ID;
- `http.request.method`;
- `url.path` (query parameters and request bodies are deliberately omitted);
- `http.response.status_code`;
- `http.server.request.duration_ms`.

The values are local to the current FastAPI request, so concurrent requests do not share or overwrite one another. The request ID is also returned in the `X-Request-ID` response header.

### Verify logs

1. Deploy/restart the application with the variables above.
2. Generate a log by opening the application or requesting its health endpoint:

   ```bash
   curl https://demo.semant.cz/health
   ```

3. Open `https://lgtm.semant.cz/`, select **Explore**, and choose the **Loki** data source.
4. Select a recent time range and run:

   ```logql
   {service_name="semant-demo-app", deployment_environment_name="production"} |= "HTTP request completed"
   ```

5. Expand a result. The request fields should be visible under **Structured metadata**. OpenTelemetry dots are normalized to underscores in Loki, for example `http.request.method` becomes `http_request_method`.

To filter a structured field, use for example:

```logql
{service_name="semant-demo-app", deployment_environment_name="production"} | http_response_status_code =~ "5.."
```

For `test-main`, use `deployment_environment_name="test-main"`; for PR 123, use `deployment_environment_name="test-pr-123"`. If no result is shown, first check the application container output for exporter errors and verify that it can resolve `lgtm` on the `web` Docker network. Then use a broad Loki query such as `{service_name=~".+"} |= "OpenTelemetry export enabled"` to verify whether the collector changed the service label mapping.

### Grafana configuration

Do not add an OTLP receiver as a Grafana data source. The application sends OTLP to the collector; Grafana reads the resulting logs from its Loki data source. The SemAnT LGTM deployment should already contain this data source. If **Loki** is missing in Explore, the LGTM stack administrator must provision it or check the collector's `logs` pipeline.

After the Explore query works, a basic dashboard panel can be created under **Dashboards → New → New visualization**. Choose Loki and use this query to graph completed requests per dashboard interval:

```logql
sum(count_over_time({service_name="semant-demo-app", deployment_environment_name="$environment"} |= "HTTP request completed" [$__interval]))
```

Create a dashboard variable named `environment` using Loki **Label values** for the label `deployment_environment_name`. This provides a switch between production, `test-main`, and individual `test-pr-<number>` deployments while keeping them under the same logical OpenTelemetry service. Separate dashboards can use the same fixed selectors if the team prefers a project-like view.

Use the Explore query to verify that logs arrive before relying on a dashboard panel built from them.

## Traces and metrics

All three signals are exported through the same OTLP/HTTP receiver and carry the same service, environment, and instance resource attributes:

```text
logs    -> http://lgtm:4318/v1/logs
traces  -> http://lgtm:4318/v1/traces
metrics -> http://lgtm:4318/v1/metrics
```

FastAPI instrumentation creates a server span and standard HTTP metrics for every request. Logging instrumentation adds the active trace/span context to log records. To avoid multiplying a large metric volume across many simultaneous PR deployments, system instrumentation is limited to process CPU time/utilization, memory usage, and thread count. Metrics are exported every 10 seconds.

### Verify traces in Tempo

1. Generate fresh traffic against the deployment, for example `/health`.
2. Open **Explore** in Grafana and choose the **Tempo** data source.
3. Use a TraceQL query for the deployment, for example PR 180:

   ```traceql
   { resource.service.name = "semant-demo-app" && resource.deployment.environment.name = "test-pr-180" }
   ```

4. Open a returned trace. It should contain a FastAPI server span for the requested route and its HTTP status.

### Verify log/trace correlation in Loki

Open a new request log. It should contain non-zero `trace_id` and `span_id`. Filter by the copied trace ID:

```logql
{service_name="semant-demo-app", deployment_environment_name="test-pr-180"}
  | trace_id="<trace-id>"
```

### Verify metrics in Prometheus

1. Wait at least 10 seconds after the application starts and generate several requests.
2. In Grafana Explore, choose the Prometheus-compatible metrics data source.
3. Start with a broad selector:

   ```promql
   {service_name="semant-demo-app", deployment_environment_name="test-pr-180"}
   ```

4. Use the metric browser to inspect HTTP server and `system.*`/`process.*` measurements. OTLP metric names are normalized to Prometheus-style underscores by the metrics backend.

If traces or metrics are accepted on port 4318 but do not appear in Grafana, verify that the Collector has enabled `traces` and `metrics` pipelines in addition to the already working `logs` pipeline.

### Basic usage dashboard

The backend also exports the `semant_demo.feature.requests` counter for completed, user-initiated actions. It has only these low-cardinality attributes:

- `feature`: `rag`, `search`, `summarize`, `ai_assistance`, or `tagging`;
- `authentication`: `bearer_token` when the request supplied a Bearer token, otherwise `anonymous`;
- `outcome`: `success`, `client_error` (4xx), or `server_error` (5xx).

No user ID, token, prompt, request ID, or response content is attached to the metric. This means the dashboard can show traffic with a Bearer token, but not the number or identity of unique users.

The metrics backend normalizes the counter name for Prometheus; locate it in the metric browser (normally `semant_demo_feature_requests_total`) and use it for a first dashboard. The examples deliberately scope the project and use the dashboard's single-select `environment` variable:

```promql
# Feature requests over the last 24 hours, by feature
sum by (feature) (
  increase(semant_demo_feature_requests_total{
    service_name="semant-demo-app",
    deployment_environment_name=~"$environment"
  }[24h])
)

# Server errors over the last 24 hours
sum(increase(semant_demo_feature_requests_total{
  service_name="semant-demo-app",
  deployment_environment_name=~"$environment",
  outcome="server_error"
}[24h]))

# Successful requests with a Bearer token over the last 24 hours
sum(increase(semant_demo_feature_requests_total{
  service_name="semant-demo-app",
  deployment_environment_name=~"$environment",
  authentication="bearer_token",
  outcome="success"
}[24h]))
```

For the 24-hour dashboard, use `[30m]`, bars aligned **Before**, and a minimum interval of `30m`. For a 30-day dashboard, use `[1d]` and a minimum interval of `1d`. `increase()` can return fractional values because Prometheus extrapolates counter samples at the window boundaries; use `round(...)` when the panel represents a count of actions.

### Feature duration percentiles

Use the custom feature histogram—not a generic `http_server_*` metric—for the user-action latency panel. Generic HTTP metrics also include technical traffic and may be emitted by other services in a shared metrics store.

Create three queries in one time-series panel, with a 30-minute window for the 24-hour view:

```promql
# p50; duplicate for p95 and p99 by changing 0.50 to 0.95 / 0.99
histogram_quantile(
  0.50,
  sum by (le) (
    increase(semant_demo_feature_request_duration_seconds_bucket{
      service_name="semant-demo-app",
      deployment_environment_name=~"$environment"
    }[30m])
  )
)
```

Name the query results `p50`, `p95`, and `p99`; display them in milliseconds with a minimum of zero. A point at 10:00 summarizes actions completed from 09:30 to 10:00. No completed classified action in that window means that a percentile is undefined: render it as a gap, never as zero milliseconds. p50 is typical latency, p95 is the slower tail, and p99 is the slowest one percent.

## Extending telemetry

Before adding a signal, decide what operational question it answers. Prefer a small number of stable, documented measurements over collecting every value available in a request. Never put a user ID, email, token, request ID, prompt, generated answer, document ID, full URL, or exception message in a metric attribute; those values create high-cardinality metrics and/or expose data.

### Add a metric

1. Add the instrument once in `initialize_opentelemetry()` in `semant_demo/opentelemetry.py`. Reuse the existing `meter`; do not create another provider or exporter.
2. Choose the type deliberately: a `Counter` for events that only increase, a `Histogram` for a size or duration where percentiles matter, and an observable gauge only for an instantaneous value.
3. Give the metric a namespaced, unit-aware name such as `semant_demo.rag.documents.retrieved` or `semant_demo.llm.request.duration` with unit `s`.
4. Keep metric attributes low-cardinality. Good examples: `operation`, `provider`, `model` from a controlled configuration, `outcome`. Bad examples: user input, document UUID, URL query string, request ID, exception text.
5. Record it at the domain boundary where the outcome and duration are known. For example, feature metrics are recorded after `call_next()` in the HTTP middleware; an LLM metric belongs around the actual provider call.
6. Add a unit test that verifies classification and attributes, and document its expected Prometheus name and query here.
7. Deploy, create the relevant traffic, wait one export interval, then find the metric in Prometheus before creating a dashboard panel.

Minimal pattern:

```python
# In initialize_opentelemetry(), once
rag_duration = meter.create_histogram(
    "semant_demo.rag.request.duration",
    unit="s",
    description="Duration of completed RAG requests.",
)

# At the completed domain operation
rag_duration.record(
    elapsed_seconds,
    attributes={"outcome": "success", "operation": "answer"},
)
```

### Add a trace/span

FastAPI already creates the outer server span. Add child spans only around operations that help answer *where time or an error was spent*: a RAG retrieval, Weaviate query, embedding request, LLM request, or important background job.

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("rag.retrieve") as span:
    span.set_attribute("rag.strategy", "hybrid")
    span.set_attribute("rag.top_k", 10)
    results = await retrieve_chunks(...)
    span.set_attribute("rag.results.count", len(results))
```

The active FastAPI span becomes the parent automatically. Use stable, non-sensitive attributes; record an exception on the span when it is handled, then re-raise or set an error status according to the surrounding error-handling policy. Do not add a prompt, answer, authorization header, raw query, document text, or user identity without an explicit privacy decision.

### Add a log field

Use the ordinary Python logger. The configured `LoggingInstrumentor` automatically adds the active trace and span context, so do not manually copy trace IDs.

```python
logging.getLogger(__name__).info(
    "RAG retrieval completed",
    extra={"rag.results.count": len(results), "rag.strategy": "hybrid"},
)
```

Use a stable event message and small structured fields. Request bodies, prompts, answers, tokens, passwords, JWTs, API keys, and full exception payloads must not be logged by default. If a log must be correlated with a request, rely on the middleware's `request.id` and the automatic trace context.

### Existing export path

The OTLP exporters, Collector pipelines, and Grafana data sources are already configured. A normal application change only writes a log, records a metric, or creates a span through the existing logger, meter, or tracer shown above; the configured exporter sends it through the existing path automatically.

Do not create another provider/exporter, change Collector configuration, or add an OTLP receiver as a Grafana data source when adding an application signal.
