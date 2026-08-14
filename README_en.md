# LibreChat Code Interpreter API (Custom RCE)

A secure, sandbox-based Code Interpreter API for LibreChat. It provides a backend to dynamically manage isolated Docker containers per session, allowing safe execution of untrusted code.

## Overview

This API provides endpoints compliant with LibreChat's Code Interpreter specification (`/exec`, `/upload`, `/download`, `/files`). It executes user code within dedicated Docker images with strictly enforced resource limits and network isolation.

It is compatible with both cloud-based providers (Gemini, OpenAI, etc.) and local LLMs (Ollama, etc.).

## Key Features & Specifications

- **Multi-language Support**: Supports execution of Python, Bash, and R.
- **Automatic Inline Graph Rendering**: Automatically detects graphs generated via Matplotlib/Seaborn (`.png`, `.jpg`, `.svg`, `.webp`), encodes them to Base64, and displays them inline in the LibreChat UI.
- **Sandbox Isolation**: Each session runs in an independent, non-root (`sandboxuser: 1000`) Docker container with memory and CPU limits.
- **Session Persistence**: Maintains filesystem state and nested directory structures across multiple messages within a session.
- **Robust Concurrency Control**: Per-session locking (`WeakrefRLock`) and starting session tracking (`pending_sessions`) fully prevent race conditions at max capacity.
- **Defense-in-Depth Security**:
  - Timing attack-resistant authentication via `LIBRECHAT_CODE_API_KEY` (`secrets.compare_digest`).
  - Least-privilege Docker API access through Docker Socket Proxy (direct socket mounting prohibited).
  - Secure code injection via `tarfile` (`put_archive`) and automatic temporary file cleanup (prevents command line injection).
  - Multi-layer directory traversal protection using `sanitize_id` and `Path.is_relative_to`.
  - Secure HTTP headers (HSTS, nosniff, DENY, XSS-Protection).
  - Explicit CORS whitelist validation (wildcard `*` prohibited).
- **Efficient Mapping**: Scalable $O(N)$ file ID mapping per session fully compliant with LibreChat's 21-character Nanoid validation.
- **Nginx Reverse Proxy / SSL / Artifacts Integration**: HTTPS termination via SAN self-signed/CA certificates and Sandpack Bundler integration (port 8443) for React/HTML UI rendering.
- **GPU Support**: Optional support for GPU-accelerated computing using CUDA-enabled images (`Dockerfile.rce.gpu`).

## Prerequisites

- **Docker**: Engine must be installed and running.
- **Python 3.13+**: Required for the host API (development only).
- **uv**: Recommended for package and virtual environment management.

---

## Setup Instructions

### A. Full-stack Configuration (LibreChat + API + DB + Nginx)

1.  **Environment Variables**:
    ```bash
    cp .env.librechat .env
    ```
    Ensure `JWT_SECRET`, `CREDS_KEY`, and `LIBRECHAT_CODE_API_KEY` are updated with unique, secure values.

2.  **Prepare Sandbox Image**:
    ```bash
    docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
    ```

3.  **Start Services**:
    ```bash
    docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
    ```

### B. Standalone API Deployment (Integration with existing LibreChat)

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
docker compose up -d --build
```
Configure `LIBRECHAT_CODE_BASEURL` and `LIBRECHAT_CODE_API_KEY` in your LibreChat's `.env`.

### C. GPU-enabled Configuration (Optional)

```bash
docker build -f Dockerfile.rce.gpu -t custom-rce-kernel:gpu .
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | (Required) | Shared key for API authentication. |
| `DISABLE_CODE_API_AUTH` | `false` | If set to `true`, disables (skips) API key validation. Useful for testing or local setups. |
| `DOCKER_HOST` | (Env dependent / `tcp://docker-proxy:2375`) | Docker Socket Proxy or daemon endpoint. |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | Docker image used for sandbox containers. |
| `RCE_GPU_ENABLED` | `false` | Set to `true` to enable NVIDIA GPU pass-through. |
| `RCE_MEM_LIMIT` | `512m` | Memory limit per container. |
| `RCE_CPU_LIMIT` | `500000000` | CPU quota per container (0.5 CPU). |
| `RCE_MAX_SESSIONS` | `100` | Maximum number of concurrent sessions. |
| `RCE_SESSION_TTL` | `3600` | Session time-to-live before automatic cleanup (seconds). |
| `RCE_NETWORK_ENABLED` | `false` | Enable/disable external network access for sandboxes (`false` recommended for security). |
| `RCE_DATA_DIR` | (None) | Host path for data persistence (Volume Mount mode). |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3080` | Comma-separated CORS origin whitelist (wildcard `*` prohibited). |

---

## Storage Modes

1.  **Standard Mode (put_archive)**:
    Default behavior when `RCE_DATA_DIR` is not set. Files are transferred via Docker API. Works without special host permissions.
2.  **Volume Mount Mode**:
    Enabled by setting `RCE_DATA_DIR` to an absolute host path. Provides faster file access and persistence on the host.
    *Note: Host directory must be writable by UID 1000.*

---

## Development & Testing

This project is built using Test-Driven Development (TDD) and includes a comprehensive test suite of **311 tests**.

Run the test suite with:

```bash
# Run all tests in a single command
LIBRECHAT_CODE_API_KEY=test-secret-key uv run pytest tests/ -v
```

> **Note**: Always provide a dummy API key via `LIBRECHAT_CODE_API_KEY` when running tests; otherwise, the FastAPI startup validation will fail.

Test Coverage:
- API authentication, timing-attack resistance, and endpoint routing
- Multi-language code execution (Python/Bash/R) and AST expression evaluation
- File processing for images (PNG/JPEG/SVG/WebP), PDFs, Office docs, ZIPs, CSV/Parquet
- Security validation: path traversal, double extension, and CRLF header injection
- High-concurrency session management, race condition protection, resource recovery, and TTL cleanup

---

## Troubleshooting (LibreChat Integration & Configuration)

If you encounter issues when integrating this Code Interpreter with LibreChat, follow the steps below to adjust your configuration.

### 1. `401 Unauthorized (Invalid API Key)` Error
If the API container logs show `Received key: None, Expected key: your_secret_key` with a warning message, the API key header is missing from the LibreChat request.

**【Solution】**:
Even in newer LibreChat releases, some tools occasionally omit the `x-api-key` header. You can safely bypass this by disabling API key validation while restricting the API port exposure to localhost loopback (`127.0.0.1`):

1. **Restrict External Port Exposure**:
   Ensure `docker-compose.yml` binds the API port to `127.0.0.1` (default setting):
   ```yaml
   ports:
     - "127.0.0.1:8000:8000"
   ```
2. **Disable API Key Authentication**:
   Add the following to your `.env`:
   ```env
   DISABLE_CODE_API_AUTH=true
   ```

Rebuild and recreate the container:
```bash
docker compose -f docker-compose.yml -f docker-compose.librechat.yml build --no-cache code-interpreter-api
docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d --force-recreate
```

### 2. External Access Issues (Changing Host Port to 3000)
If you cannot access LibreChat from other devices on the same local network, change the port mapping from `3080` to **`3000`** in `docker-compose.librechat.yml`:
* `docker-compose.librechat.yml` ports configuration under `librechat` service:
  ```yaml
  ports:
    - "3000:3080" # Maps host port 3000 to container port 3080
  ```
* Restart the containers:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
  ```

### 3. Ollama Models Not Appearing in the UI Selection Menu
Defining `endpoints.ollama` directly in `librechat.yaml` triggers Zod validation errors and breaks the config parsing. Furthermore, if Ollama is running in a different Docker Compose project/network, the container cannot resolve the host name `ollama`.

**【Solution】**:
Ollama officially supports OpenAI-compatible API paths. Integrate it as a custom endpoint instead:
1. **Modify `librechat.yaml`**:
   ```yaml
   endpoints:
     custom:
       - name: "Ollama"
         apiKey: "ollama"
         baseURL: "${OLLAMA_BASE_URL}/v1"
         models:
           default: ["qwen3.5:4b"]
           fetch: true
         titleConvo: true
         summarize: true
         modelDisplayLabel: "Ollama"
   ```
2. **Set connection via host gateway in `.env`**:
   ```env
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   ```
3. **Map `host.docker.internal` inside `docker-compose.librechat.yml`**:
   Add the following `extra_hosts` under `librechat` service:
   ```yaml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```
* Restart the containers.
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
  ```

---

## Documentation (OKF Knowledge Base)

For detailed technical specifications, architecture designs, and infrastructure guides, refer to the OKF knowledge base in `docs/`:

* **[Knowledge Index (docs/README.md)](./docs/README.md)**: Main documentation index
* **[System Overview (docs/architecture/overview.md)](./docs/architecture/overview.md)**: Architecture design and container execution flow
* **[Security Model (docs/architecture/security.md)](./docs/architecture/security.md)**: Defense-in-depth, Socket Proxy, and isolation design
* **[Concurrency Control (docs/architecture/concurrency.md)](./docs/architecture/concurrency.md)**: `WeakrefRLock` and `pending_sessions` race condition prevention
* **[Multi-Language Code Execution (docs/domain/code-execution.md)](./docs/domain/code-execution.md)**: AST parsing, Japanese Matplotlib support, and inline graph capture
* **[Session Resolution & Fallback (docs/domain/session-resolution.md)](./docs/domain/session-resolution.md)**: Automatic session ID resolution specification
* **[File Handling & UTF-8 (docs/domain/file-handling.md)](./docs/domain/file-handling.md)**: $O(N)$ mapping, nested directory scanning, RFC 5987 compliance
* **[Docker Setup & Storage Modes (docs/infrastructure/docker-setup.md)](./docs/infrastructure/docker-setup.md)**: Deployment guides and storage selection
* **[Sandbox Image Design (docs/infrastructure/sandbox-image.md)](./docs/infrastructure/sandbox-image.md)**: Multi-stage CPU/GPU Dockerfile specifications
* **[Reverse Proxy & SSL Design (docs/infrastructure/reverse-proxy.md)](./docs/infrastructure/reverse-proxy.md)**: Nginx SSL termination, SAN certs, and Artifacts
* **[Configuration Reference (docs/infrastructure/configuration.md)](./docs/infrastructure/configuration.md)**: Environment variables and `librechat.yaml` reference


