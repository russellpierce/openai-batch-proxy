AI Authored, some human auditing of functionality and editing of documentation

# OpenAI-Compatible Chat Completion Server

A FastAPI server that exposes an OpenAI-compatible `/v1/chat/completions` endpoint, routing requests to a customizable workflow function.

## Features

- OpenAI-compatible API endpoints (`/v1/chat/completions`, `/v1/models`)
- API key authentication
- Configurable via YAML
- Docker deployment ready
- Pre-commit hooks for code quality

## Quick Start

### With Docker Compose

```bash
# Copy example API keys file and add your keys
cp api_keys.txt.example api_keys.txt

# Start the server
docker compose up --build
```

### Local Development

```bash
# Install dependencies
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install

# Copy example API keys file
cp api_keys.txt.example api_keys.txt

# Start the server
uv run uvicorn skeleton_open_ai.main:app --reload
```

## Configuration

All configuration is in `config.yml`:

```yaml
# Server binding
server:
  host: "0.0.0.0"
  port: 8000

# Authentication
auth:
  api_keys_file: "api_keys.txt"

# Available models
models:
  - default_workflow

# CORS settings
cors:
  allow_origins:
    - "*"
```

### API Key Management

Add API keys to `api_keys.txt` (one per line, comments start with `#`):

```bash
# Generate a secure key
python -c "import secrets; print('sk-' + secrets.token_hex(32))"
```

## API Reference

### Health Check

```bash
curl http://localhost:8000/health
```

Response: `{"status": "healthy"}`

### List Models

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer sk-your-api-key"
```

### Chat Completion

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default_workflow",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Implementing Your Workflow

Edit `src/skeleton_open_ai/workflow.py` to implement your AI logic:

```python
def run_workflow(messages: list[ChatMessage], model: str) -> str:
    """
    Implement your AI workflow here.
    
    Args:
        messages: The conversation history from the request
        model: The model name requested by the client
        
    Returns:
        The assistant's response as a string
    """
    # Your implementation here
    return "Your response"
```

## Development

### Running Tests

```bash
uv run pytest
```

### Type Checking

```bash
uv run mypy src tests
```

### Linting

```bash
uv run ruff check src tests
```

### Format Code

```bash
uv run ruff format src tests
```

### Run All Pre-commit Hooks

```bash
uv run pre-commit run --all-files
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | `config.yml` | Path to configuration file |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `API_PORT` | `8000` | Port for Docker Compose |

## License

MIT
