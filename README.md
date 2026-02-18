# LibreChat Custom Code Interpreter API

A secure, sandboxed Code Interpreter API for LibreChat, enabling Python code execution within isolated Docker containers. Supports Ollama local models for fully offline AI + code execution.

## Features

- **Sandboxed Execution**: Code runs in isolated Docker containers with configurable memory/CPU limits and no network access by default.
- **LibreChat Compatible**: Fully aligns with LibreChat's Code Interpreter API spec (`/exec`, `/upload`, `/download`, `/files`).
- **Session Persistence**: Maintains filesystem state per session (uploaded files and generated outputs are preserved).
- **Customizable Environment**: Pre-installed scientific libraries (`pandas`, `numpy`, etc.) via a custom Docker image.
- **Ollama Integration**: Works with local Ollama models (e.g. `qwen2.5-coder:3b`) for fully offline operation.
- **GPU Support**: Optional CUDA-enabled sandbox image for GPU-accelerated code execution.
- **Secure API**: Protected by API Key authentication and a Docker Socket Proxy.
- **Configurable via Env Vars**: All resource limits and behavior controlled by environment variables.

## Prerequisites

- **Docker**: Must be installed and running.
- **Python 3.13+**: For local development (optional if using Docker Compose).
- **uv**: Recommended for Python package management.

---

## Quick Start: Full LibreChat Stack with Ollama

This is the recommended setup for running LibreChat + Code Interpreter + Ollama together.

### 1. Build the Sandbox Image

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
```

### 2. Connect Ollama to the LibreChat Network

If you have Ollama running as a Docker container:

```bash
docker network connect librechat-network ollama
```

### 3. Start the Full Stack

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d
```

LibreChat will be available at **http://localhost:3080**.

### 4. Configure Environment

Copy and edit the template:

```bash
cp .env.librechat .env
# Edit .env with your actual secrets (JWT_SECRET, CREDS_KEY, etc.)
```

---

## Setup: Code Interpreter API Only

### Docker Compose (Recommended)

```bash
# Build sandbox image first
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .

# Start the API
docker compose up -d --build
```

Configure LibreChat to use it:
```dotenv
LIBRECHAT_CODE_BASEURL=http://host.docker.internal:8000
LIBRECHAT_CODE_API_KEY=your_secret_key
```

### Local Development

```bash
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## GPU Support

For CUDA-accelerated code execution:

```bash
# Build GPU-enabled sandbox image
docker build -f Dockerfile.rce.gpu -t custom-rce-kernel:gpu .

# Start with GPU support
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## Configuration

All settings are controlled via environment variables:

| Variable | Default | Description |
|---|---|---|
| `CUSTOM_RCE_API_KEY` | `your_secret_key` | API key for authentication |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | Docker image for sandboxes |
| `RCE_MEM_LIMIT` | `512m` | Memory limit per sandbox |
| `RCE_CPU_LIMIT` | `500000000` | CPU quota in nanoseconds (0.5 CPU) |
| `RCE_NETWORK_ENABLED` | `false` | Allow network access in sandbox |
| `RCE_GPU_ENABLED` | `false` | Enable GPU passthrough |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/exec` | Execute Python code |
| `POST` | `/run/exec` | Alias for `/exec` (LibreChat compat) |
| `POST` | `/upload` | Upload files to a session |
| `GET` | `/files/{session_id}` | List files in a session |
| `GET` | `/download/{session_id}/{filename}` | Download a file |

### Request Body for `/exec`

```json
{
  "code": "print(2 + 2)",
  "lang": "py",
  "session_id": "optional-uuid",
  "user_id": "optional-user-id"
}
```

### Response

```json
{
  "stdout": "4\n",
  "stderr": "",
  "exit_code": 0,
  "output": "4\n",
  "files": []
}
```

---

## Running Tests

```bash
uv run pytest tests/ -v
```

All 12 tests should pass, covering:
- API authentication and endpoints
- Kernel manager session lifecycle
- Container recovery on failure
- Docker socket security proxy

---

## Architecture

```
LibreChat (port 3080)
    │
    ├── MongoDB (session storage)
    ├── Meilisearch (search)
    └── Code Interpreter API (port 8000)
            │
            ├── Docker Socket Proxy (security layer)
            └── RCE Sandbox Containers (isolated Python)

Ollama (port 11434) ──── librechat-network ────► LibreChat
```
