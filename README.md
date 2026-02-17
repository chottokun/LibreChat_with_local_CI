# LibreChat Custom Code Interpreter API

This project provides a secure, sandboxed Code Interpreter API for LibreChat, enabling Python code execution within isolated Docker containers.

## Features

- **Sandboxed Execution**: Code runs in isolated Docker containers with no network access.
- **Session Persistence**: Maintains filesystem state per session (files created in one run are available in the next).
- **Customizable Environment**: Pre-installed scientific libraries (`pandas`, `numpy`, `scipy`, `matplotlib`) via a custom Docker image.
- **Secure API**: Protected by API Key authentication.

## Prerequisites

- **Docker**: Must be installed and running.
- **Python 3.11+**: For local development (optional if using Docker Compose).
- **uv**: Recommended for Python package management (optional if using Docker Compose).

---

## Setup & Installation

### 1. Build the Sandbox Environment (Important)

Before running the API server, you must build the Docker image that will be used for sandboxed code execution.

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
```
*This image (`custom-rce-kernel`) contains the Python environment and libraries (pandas, etc.) used to execute user code.*

---

## Usage Method 1: Docker Compose (Recommended)

This method runs the API server itself in a Docker container.

1.  **Start the API Server:**
    ```bash
    docker-compose up -d --build
    ```

2.  **Configuration for LibreChat:**
    Update your LibreChat `.env` file:
    ```dotenv
    # If LibreChat is also in Docker:
    LIBRECHAT_CODE_BASEURL=http://host.docker.internal:8000/run/exec
    
    # If LibreChat is running locally on the host:
    # LIBRECHAT_CODE_BASEURL=http://localhost:8000/run/exec
    
    LIBRECHAT_CODE_API_KEY=your_secret_key
    ```
    *Note: `host.docker.internal` allows the LibreChat container to talk to the API container via the host's port mapping.*

3.  **Stop the Server:**
    ```bash
    docker-compose down
    ```

---

## Usage Method 2: Local Execution with `uv`

This method runs the API server directly on your host machine.

1.  **Install Dependencies:**
    ```bash
    uv sync
    # Or manually: uv add fastapi uvicorn pydantic docker
    ```

2.  **Start the Server:**
    ```bash
    uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```

3.  **Configuration for LibreChat:**
    Update your LibreChat `.env` file. Since the API is running on your host IP:
    ```dotenv
    # Replace with your actual Host IP (e.g., 192.168.1.x)
    LIBRECHAT_CODE_BASEURL=http://YOUR_HOST_IP:8000/run/exec
    LIBRECHAT_CODE_API_KEY=your_secret_key
    ```

---

## Technical Details

### Architecture

1.  **FastAPI Gateway (`main.py`)**:
    -   Receives code execution requests from LibreChat.
    -   Authenticates requests using `X-API-Key`.
    -   Manages Docker containers via `docker-py` SDK.

2.  **Sandbox Containers**:
    -   Based on `custom-rce-kernel:latest` image.
    -   **Isolation**: `network_disabled=True` prevents internet access.
    -   **Resource Limits**: 0.5 CPU cores, 512MB RAM.
    -   **Persistence**: The container remains running for the duration of the session (until stopped/removed), allowing file persistence in `/usr/src/app` or `/tmp`.
    -   **Execution**: Uses `docker exec` to run Python code as a new process within the container. Note that variable state (memory) is not persisted between calls, but files are.

### File Structure

-   `main.py`: The API server application.
-   `Dockerfile.rce`: Definition for the sandboxed execution environment (contains libraries).
-   `Dockerfile.api`: Definition for the API server container (for Docker Compose).
-   `rce_requirements.txt`: Python libraries installed in the sandbox.
-   `docker-compose.yml`: Service definition for running the API server.
