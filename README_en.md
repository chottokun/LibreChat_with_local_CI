# LibreChat Custom Code Interpreter API

A secure, sandboxed Code Interpreter API for LibreChat, enabling Python code execution within isolated Docker containers. This enables your LLMs to run code, generate data, and create files seamlessly within the LibreChat interface. 

Supports Ollama local models for fully offline AI + code execution, as well as cloud providers like Google Gemini.

## 🚀 Features

- **Sandboxed Execution**: Python code runs in isolated Docker containers (`custom-rce-kernel`) with configurable memory/CPU limits and no network access by default.
- **LibreChat Native Integration**: Fully aligns with LibreChat's Code Interpreter API spec (`/exec`, `/upload`, `/download`, `/files`). Generated files appear as native UI attachments in the chat block.
- **Session Persistence**: Maintains filesystem state per session. Uploaded files and generated outputs are preserved and accessible across multiple messages.
- **Customizable Environment**: Pre-installed scientific libraries (`pandas`, `matplotlib`, `numpy`, etc.) via a custom Docker image.
- **Offline & Local AI Support**: Works perfectly with local Ollama models (e.g. `qwen2.5-coder:3b`) for fully offline operation.
- **GPU Acceleration**: Optional CUDA-enabled sandbox image for GPU-accelerated code execution.
- **Secure Architecture**: Protected by API Key authentication and a Docker Socket Proxy.
- **Configurable via Env Vars**: All resource limits and behavior controlled by `.env` variables.

## 📋 Prerequisites

- **Docker**: Must be installed and running.
- **Python 3.13+**: For local development (optional if deploying via Docker Compose).
- **uv**: Recommended for Python package management.

---

## ⚡ Quick Start: Full LibreChat Stack

This is the recommended setup for running LibreChat + Code Interpreter API together.

### 1. Configure Environment Variables

Copy the template map to configure your environment:

```bash
cp .env.librechat .env
```

Make sure to update the following **Required Settings** in your `.env` for security:
- **`JWT_SECRET` / `JWT_REFRESH_SECRET`**: Random strings for JWT authentication.
- **`CREDS_KEY` / `CREDS_IV`**: Keys for encrypting credentials.
- **`LIBRECHAT_CODE_API_KEY`**: A shared secret key between LibreChat and this API.

### 2. Build the Sandbox Image

You must build the base image that the API uses to spawn isolated Python execution environments.

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
```

### 3. Start the Full Stack

Launch MongoDB, Meilisearch, the Code Interpreter API, and LibreChat:

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d
```

LibreChat will be available at **http://localhost:3080**.

### 4. Connect Local Models (Optional: Ollama)

If you have Ollama running as a separate Docker container and want to use it with LibreChat:

```bash
docker network connect librechat-network ollama
```
*(Ensure your `.env` contains the correct `OLLAMA_BASE_URL`)*

---

## 🛠️ Setup: Code Interpreter API Only

If you already have a LibreChat instance running elsewhere, you can run just the API.

### Using Docker Compose (Recommended)

```bash
# Build sandbox image first
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .

# Start the API and Docker Socket Proxy
docker compose up -d --build
```

**Configure your separate LibreChat instance to use this API:**
Add these to your LibreChat `.env`:
```dotenv
LIBRECHAT_CODE_BASEURL=http://<YOUR_API_HOST>:8000
LIBRECHAT_CODE_API_KEY=your_secret_key
```

### Local Development (Without Docker Compose)

```bash
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🏎️ GPU Support

For CUDA-accelerated code execution inside the sandboxes:

```bash
# Build GPU-enabled sandbox image
docker build -f Dockerfile.rce.gpu -t custom-rce-kernel:gpu .

# Start with GPU support enabled
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## ⚙️ Configuration Flags

All settings are controlled via environment variables in the `.env` file:

| Variable | Default | Description |
|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | (Required) | API key for authentication (Must be set) |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | Docker image to spawn for sandboxes |
| `RCE_MEM_LIMIT` | `512m` | Memory limit per sandbox container |
| `RCE_CPU_LIMIT` | `500000000` | CPU quota in nanoseconds (0.5 CPU) |
| `RCE_MAX_SESSIONS` | `100` | Maximum number of concurrent sandbox containers |
| `RCE_NETWORK_ENABLED` | `false` | Allow internet access inside the sandbox |
| `RCE_GPU_ENABLED` | `false` | Enable GPU passthrough to the sandbox |
| `RCE_DATA_DIR` | (None) | Host path for session data persistence (must be mounted, see below) |

### 📁 File Persistence & Storage Modes

This API supports two modes for handling file uploads and generated data.

#### 1. Standard Mode (Default: `put_archive`)
This mode is active when `RCE_DATA_DIR` is not set (or commented out) in your `.env`.
- **Pros**: Works "out of the box" without extra configuration or permission headaches.
- **Cons**: Slightly slower for very large files.
- **How it works**: Files are streamed directly into containers via the Docker API.

#### 2. High Performance Mode (Advanced: Volume Mounting)
Uses host directory mounting for persistence and faster file access. Recommended for heavy data analysis.

**Setup Steps:**
1. **Create Directory**: Create a directory on your host machine.
   ```bash
   mkdir -p sessions
   ```
2. **Set Permissions**: Ensure the API container (UID 1000) has write access. **Required on Linux.**
   ```bash
   sudo chown -R 1000:1000 sessions
   ```
3. **Configure `.env`**: Set the **absolute path** to your directory.
   ```dotenv
   RCE_DATA_DIR=/home/user/Project/sessions
   ```
4. **Restart**: Run `docker compose up -d` to apply.

> [!TIP]
> If there is a permission error or invalid path in Volume mode, the API will automatically fall back to **Standard Mode**, ensuring your chat remains functional.

---

## 🏗️ Architecture

```text
LibreChat (port 3080)
    │
    ├── MongoDB (session/chat storage)
    ├── Meilisearch (search)
    └── Code Interpreter API (port 8000)
            │
            ├── Docker Socket Proxy (security layer)
            └── RCE Sandbox Containers (isolated Python environments)
```

---

## 🐛 Troubleshooting

Please refer to the detailed **[LibreChat Integration Guide](docs/librechat_integration_guide.md)** in the `docs/` folder for solutions to common issues, including:
- "Network Error" when downloading files.
- `400 Bad Request` or LibreChat ID validation failures.
- Nginx reverse proxy routing issues.
- Browser-specific frontend bugs with Blob URLs.

---

## 🧪 Running Tests

```bash
uv run pytest tests/ -v
```

The test suite covers:
- API authentication and endpoint schemas.
- Kernel manager session creation and lifecycle.
- Container recovery and orphan cleanup.
- Docker socket security proxy validation.
