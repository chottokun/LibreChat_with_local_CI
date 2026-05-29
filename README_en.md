# LibreChat Code Interpreter API (Custom RCE)

A secure, sandbox-based Code Interpreter API for LibreChat. It provides a backend to dynamically manage isolated Docker containers per session, allowing safe execution of untrusted code.

## Overview

This API provides endpoints compliant with LibreChat's Code Interpreter specification (`/exec`, `/upload`, `/download`, `/files`). It executes user code within dedicated Docker images with strictly enforced resource limits and network isolation.

It is compatible with both cloud-based providers (Gemini, OpenAI, etc.) and local LLMs (Ollama, etc.).

## Key Features & Specifications

- **Multi-language Support**: Supports execution of Python, Bash, and R.
- **Sandbox Isolation**: Each session runs in an independent Docker container with memory and CPU limits.
- **Session Persistence**: Maintains filesystem state across multiple messages within a session.
- **Security**:
  - Mandatory authentication via `LIBRECHAT_CODE_API_KEY`.
  - Secure Docker API access through Docker Socket Proxy.
  - Built-in protection against Path Traversal vulnerabilities in file operations.
- **Efficient Mapping**: Scalable $O(N)$ file ID mapping per session.
- **GPU Support**: Optional support for GPU-accelerated computing using CUDA-enabled images.

## Prerequisites

- **Docker**: Engine must be installed and running.
- **Python 3.13+**: Required for the host API (development only).
- **uv**: Recommended for package and virtual environment management.

---

## Setup Instructions

### A. Full-stack Configuration (LibreChat + API + DB)

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

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | (Required) | Shared key for API authentication. |
| `DISABLE_CODE_API_AUTH` | `false` | If set to `true`, disables (skips) API key validation. Useful for testing, local setups, or bypassing LibreChat client bugs. |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | Docker image used for sandbox containers. |
| `RCE_MEM_LIMIT` | `512m` | Memory limit per container. |
| `RCE_CPU_LIMIT` | `500000000` | CPU quota per container (0.5 CPU). |
| `RCE_MAX_SESSIONS` | `100` | Maximum number of concurrent sessions. |
| `RCE_NETWORK_ENABLED` | `false` | Enable/disable external network access for sandboxes. |
| `RCE_DATA_DIR` | (None) | Host path for data persistence (Volume Mount mode). |

---

## Storage Modes

1.  **Standard Mode (put_archive)**:
    Default behavior when `RCE_DATA_DIR` is not set. Files are transferred via Docker API. Works without special host permissions.
2.  **Volume Mount Mode**:
    Enabled by setting `RCE_DATA_DIR` to an absolute host path. Provides faster file access and persistence on the host.
    *Note: Host directory must be writable by UID 1000.*

---

## Development & Testing

This project is built using Test-Driven Development (TDD) and includes a suite of over 100 tests.

```bash
# Run tests
uv run pytest tests/
```

Test Coverage:
- API authentication and endpoint schema validation.
- Success and error paths for Multi-language execution (Python/Bash/R).
- Security validation, including Path Traversal prevention.
- Parallel session management and resource recovery under load.

---

## Troubleshooting (LibreChat Integration Issues)

If you encounter issues when integrating this Code Interpreter with LibreChat, follow the steps below to resolve them.

### 1. `401 Unauthorized (Invalid API Key)` Error
Certain versions or configurations of LibreChat may fail to inject the `x-api-key` or `Authorization` header during API requests (leaving the key empty). 
If the API container logs show `Received key: None, Expected key: your_secret_key` with a warning message, you are affected by this bug.

**【Solution】**:
Add the following line to your `.env` file to skip (bypass) API key validation. This is safe to use in a local network or Docker bridge network setup.
```env
DISABLE_CODE_API_AUTH=true
```
After making changes, rebuild the image without cache and recreate the containers:
```bash
docker compose -f docker-compose.yml -f docker-compose.librechat.yml build --no-cache code-interpreter-api
docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d --force-recreate
```

### 2. External Access Issues (Changing Host Port to 3000)
If you cannot access LibreChat from other devices on the same local network, change the port mapping from the default `3080` to **`3000`** in `docker-compose.librechat.yml`:
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

### 4. Japanese Filename Corruption (Cause & Current Limitations)
When uploading files with non-ASCII characters (e.g., Japanese, Chinese) from the browser, filenames may be replaced with underscores (`_`) or corrupted. This is caused by historical Latin1 encoding assumptions and sanitization routines in LibreChat's upstream file-upload middleware (`multer`/`busboy`) (Issue #8792).

**Custom RCE API Mitigations**:
* To correctly handle non-ASCII filenames within the sandbox, the sandbox container locale is set to UTF-8 (`LANG=C.UTF-8`, `LC_ALL=C.UTF-8`). 
* The API avoids shell-dependent `ls` commands and uses Python's `os.listdir` to fetch lists robustly.
* For file downloads, the API responds with RFC 5987-compliant `Content-Disposition` headers to ensure browsers decode the filenames correctly.

**Current Limitations**:
Although the API is fully compatible with UTF-8 filenames, if the upstream LibreChat client/server sanitizes or corrupts the filenames before sending them to the API, the system will record and process them with those modified/corrupted names. Resolving this entirely requires a patch on the LibreChat core codebase, or database-backed filename metadata handling in future LibreChat versions.

### 5. Frequent Container Re-creation due to Missing Session ID
When executing code without attaching files, LibreChat's client-side module (`@librechat/agents`) does not include the top-level `session_id` in its API requests. This results in the API spinning up a fresh container for every execution, introducing a latency overhead of 2-3 seconds and losing variables or files created in previous turns.

**Custom RCE API Automatic Fallbacks**:
To address this upstream limitation gracefully, this API incorporates multiple built-in fallback mechanisms (no configuration required):
1. **`user_id` Binding**: If a `user_id` is present in the request payload, the API binds the sandbox to `user_<user_id>` and reuses the container across messages.
2. **Recent Upload Reuse**: If a file upload was successfully recorded within the last 5 minutes, and a subsequent execution request lacks a `session_id`, the API automatically reuses the last upload's session ID to execute the code in the same container.

These fallbacks minimize container creation overhead, slashing execution latency to milliseconds and reliably maintaining session state.

