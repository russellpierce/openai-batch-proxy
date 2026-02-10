# openai-batch-proxy

An OpenAI API proxy that lets existing clients use the [Batch API](https://platform.openai.com/docs/guides/batch) without code changes.  This covers the following endpoints:

* /v1/chat/completions
* /v1/completions
* /v1/embeddings
* /v1/moderations
* /v1/responses

## The problem

OpenAI's Batch API offers a 50% cost reduction, but it requires a fundamentally different integration pattern: upload a JSONL file, poll for completion, then download results. Any application built against standard `/v1/chat/completions` endpoints cannot use it without significant rework.

This proxy sits between your application and OpenAI. Your application sends normal synchronous requests; the proxy translates them into batch operations behind the scenes, polls for results, and returns them as if the call were synchronous. The client never knows the difference.

> **Warning:** This project has not been used in production. It is quite possibly ill-suited for your workload. This pattern results in very long running API requests, any number of reconfigurations may be required for your client and the proxy to hold a connection open as long as is required to get a batch response (batch jobs can take minutes to hours). The disconnect/retry logic is largely untested under real conditions, and the failure modes are not well understood. The proxy does not manage the files it uploads or downloads in the batch request cycle ([Issue](https://github.com/russellpierce/openai-batch-proxy/issues/1)). Try it for yourself and create issues / PRs to improve.

See also:
* [llmbatching](https://github.com/miko-ai-org/llmbatching) - Use if you have control over your callers.  This proxy submits to batch and yields a 422 until the batch job is done.  The caller has to reissue requests in response to the 422 to get the result. Requires a database.
* [llm-proxy](https://github.com/xdrudis/llm-proxy) - Buffers and groups requests for batch processing.  Includes stats monitoring.  Covers only the /v1/chat/completions and /v1/embeddings endpoints.  Does not provide a graceful fallback if a batch times out.
* [Priority Processing](https://developers.openai.com/api/docs/guides/priority-processing) - Open AI has a `service_tier` argument for some endpoints.  The 'flex' option for that argument provides batch savings!  However, it only supports some models and some endpoints (fewer than are supported via the Batch API).

## Modes

Each route in `config.yaml` is assigned a mode:

- **passthrough** — Forwards requests directly to OpenAI. The default for any route not explicitly configured.
- **batch_proxy** — Translates synchronous requests into Batch API calls. Uses an embedded store by default, or external Redis for multi-instance deployments. Falls back to a direct API call if batch submission fails.

## Overrides

Routes can force or default request parameters before they reach OpenAI.

```yaml
routes:
  /v1/chat/completions:
    mode: batch_proxy
  /v1/responses:
    overrides:
      body:
        service_tier:
          value: "flex"
          mode: "force"    # always set, ignoring client value
        reasoning.effort:
          value: "low"
          mode: "default"  # set only if client didn't send one
```

Overrides apply to body, headers, and query parameters. Dot notation (`reasoning.effort`) is supported for nested body fields.

## API key mapping

Callers authenticate with proxy-issued keys. Each proxy key maps to an OpenAI API key in `api_keys.yaml`:

```yaml
keys:
  - caller_key: "sk-your-caller-key-here"
    openai_key: "sk-your-openai-key-here"
    retry_buffer_ttl_seconds: 86400  # optional, default 86400 (24h)
```

This keeps real OpenAI keys off client machines and lets you rotate or revoke access per caller.

## Storage backend

The batch_proxy mode needs a key-value store for retry buffering and batch tracking.

- **No `redis:` in config.yaml** — An embedded [redislite](https://github.com/yahoo/redislite) instance starts automatically. No external dependencies. Best for single-instance deployments.
- **`redis:` section present** — Connects to an external Redis server. Required when running multiple proxy instances that need to share state (e.g., behind a load balancer).

```yaml
# Single instance (no redis section needed):
server:
  host: "0.0.0.0"
  port: 8000
auth:
  api_keys_file: "api_keys.yaml"
routes:
  /v1/chat/completions:
    mode: batch_proxy

# Multi-instance (add redis section):
redis:
  url: "redis://redis-host:6379/0"
  namespace: "batch_proxy"
```

When Redis is configured, the `/health` endpoint verifies connectivity and returns `503` if Redis is unreachable.

> **Note:** The embedded redislite backend communicates via unix sockets and only works on *nix systems (Linux, macOS). On Windows, configure an external Redis server via the `redis:` section.

## Quick start

### Docker Compose

```bash
cp api_keys.yaml.example api_keys.yaml   # add your keys
docker compose up --build
```

This starts the proxy and a Redis instance.

### Local development

```bash
uv sync --all-extras
cp api_keys.yaml.example api_keys.yaml
uv run uvicorn openai_batch_proxy.main:app --reload
```

Redis is optional — omit the `redis:` section from config.yaml to use the embedded store.

## Usage

Health check (no auth required):

```bash
curl http://localhost:8000/health
```

Chat completion (use the proxy-issued `caller_key`, not the OpenAI key):

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-your-caller-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Configuration

All configuration lives in `config.yaml`. The server will not start if the file is missing or invalid.

| Environment variable | Default | Description |
|---|---|---|
| `CONFIG_PATH` | `config.yaml` | Path to configuration file |
| `LOG_LEVEL` | `INFO` | Logging level |

## Development

```bash
uv run pre-commit install          # install hooks
uv run pytest                      # tests
uv run ruff check src tests        # lint
uv run ruff format src tests       # format
uv run mypy src tests              # type check
```

## License

Apache-2.0
