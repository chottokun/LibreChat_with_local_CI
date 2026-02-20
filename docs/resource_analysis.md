# Resource Exhaustion Analysis Report: LibreChat Code Interpreter API

## 1. Executive Summary
The current implementation of the Remote Code Execution (RCE) API has several critical resource management flaws that can lead to host exhaustion (CPU, Memory, Disk) and service instability when subjected to repeated usage or long-term operation.

## 2. Identified Risks

### 2.1. Container Proliferation (Leakage)
- **Mechanism**: Every new `session_id` provided by the client triggers the creation of a new Docker container.
- **Problem**: There is no mechanism to stop or remove these containers once a session is finished.
- **Impact**: 1000 unique sessions = 1000 running containers. Even if idle, these consume kernel resources, process slots, and memory.

### 2.2. Memory Pressure
- **Mechanism**: Each container is started with a `mem_limit` (default: 512MB).
- **Problem**: While Docker uses thin provisioning, the *reservation* of memory can lead to Out-Of-Memory (OOM) conditions on the host if too many containers are spawned.
- **API Leak**: The `KernelManager.active_kernels` dictionary in `main.py` is an unbounded in-memory cache that grows indefinitely, leaking memory in the API process itself.

### 2.3. Storage Pressure
- **Mechanism**: Files uploaded via `/upload` or generated during code execution are stored in the container's writable layer.
- **Problem**: Since containers are never deleted, this disk space is never reclaimed. Malicious or accidental generation of large files can fill the host's disk.

### 2.4. Zombie Containers (Orphaned Sessions)
- **Mechanism**: The API stores the mapping of `session_id` to containers only in memory.
- **Problem**: Upon API restart, this mapping is lost.
- **Impact**:
    - Existing containers remain running on the host but are no longer managed by the API.
    - If a client reconnects with the same `session_id`, the API (having lost its memory) will spawn a *new* container for that same session, doubling the resource usage for that user.

## 3. Bold Prediction: Scalability Failure
In a production scenario with 100 active users:
- Each user creates 5 chats/sessions per day.
- API restarts once a day for deployment/maintenance.
- After 7 days: **3,500 containers** could be running on the host.
- Total potential memory reservation: **1.75 TB** (at 512MB/container).
- Host system crash is inevitable within days.

## 4. Recommended Fixes
1. **Idle Timeout (TTL)**: Implement a background task to stop and remove containers that haven't been accessed for a configurable duration (e.g., 1 hour).
2. **Session Limiting**: Impose a hard limit on the total number of concurrent active sessions.
3. **Container Recovery**: On startup, the API should scan Docker for existing managed containers to "re-adopt" them instead of creating duplicates.
4. **Persistent Labeling**: Use Docker labels to reliably identify and manage containers across API restarts.
