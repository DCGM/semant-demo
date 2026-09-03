# Observability

The observability work is intentionally split into two phases. Phase 1 provides a small end-to-end check that the application can send data to the LGTM stack. Phase 2 adds metrics and traces only after log delivery is verified.

## Phase 1: application logs in Grafana

Phase 1 is implemented. The backend sends standard Python `logging` records to the OpenTelemetry Collector over OTLP/HTTP. The collector is expected to route them to Loki.

Both committed `.env` templates use `OTEL_ENABLED=true`. CI also sets it explicitly for every deployment type so telemetry is available while testing pull requests:

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

### Verify phase 1

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

For `test-main`, use `deployment_environment_name="test-main"`; for PR 123, use `deployment_environment_name="test-pr-123"`. If no result is shown, first check the application container output for exporter errors and verify that it can resolve `lgtm` on the `web` Docker network. Then use a broad Loki query such as `{service_name=~".+"} |= "OpenTelemetry log export enabled"` to verify whether the collector changed the service label mapping.

### Grafana configuration

Do not add an OTLP receiver as a Grafana data source. The application sends OTLP to the collector; Grafana reads the resulting logs from its Loki data source. The SemAnT LGTM deployment should already contain this data source. If **Loki** is missing in Explore, the LGTM stack administrator must provision it or check the collector's `logs` pipeline.

After the Explore query works, a basic dashboard panel can be created under **Dashboards → New → New visualization**. Choose Loki and use this query to graph completed requests per dashboard interval:

```logql
sum(count_over_time({service_name="semant-demo-app", deployment_environment_name="$environment"} |= "HTTP request completed" [$__interval]))
```

Create a dashboard variable named `environment` using Loki **Label values** for the label `deployment_environment_name`. This provides a switch between production, `test-main`, and individual `test-pr-<number>` deployments while keeping them under the same logical OpenTelemetry service. Separate dashboards can use the same fixed selectors if the team prefers a project-like view.

Keep the Explore query as the acceptance criterion for phase 1; a polished dashboard belongs in phase 2, once metric names and required views have been agreed on.

## Phase 2: traces, metrics, and LLM usage

Start this phase only after the phase-1 Loki query returns data.

1. Add OTLP trace and metric exporters and FastAPI instrumentation.
2. Export HTTP request count, status, and duration plus process CPU and memory metrics. Display these from the Prometheus-compatible Grafana data source.
3. Add spans around the important RAG, Weaviate, embedding, and LLM modules so a slow request can be split into its component operations.
4. For every LLM call, record the provider, model, operation, result status, and duration; do not record prompts or generated text by default.
5. Read input/output token counts from the provider response and attach them to the LLM span with OpenTelemetry GenAI attributes such as `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. Export aggregated token metrics grouped by model and operation.
6. Correlate logs with the active trace ID so a request can be followed from FastAPI through RAG and the selected LLM.
7. Add a concurrency test that overlaps multiple FastAPI requests and verifies that trace/request context never moves from one request to another.

Suggested Grafana panels for phase 2:

- request rate and 5xx rate;
- p50/p95/p99 HTTP response duration;
- LLM calls and failures by model;
- p50/p95 LLM response duration by model;
- input/output tokens by model and operation;
- process CPU and memory;
- trace search filtered by `service.name=semant-demo-app`.

Keep model name, operation, and status as low-cardinality metric attributes. Keep request IDs, user IDs, prompts, and responses out of metric labels; request IDs belong in logs/traces, and prompt content should only be captured after an explicit privacy review.
