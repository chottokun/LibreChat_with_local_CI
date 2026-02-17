import traceback
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import docker
import os
import uuid

# 1. Authentication Scheme
API_KEY = os.environ.get("CUSTOM_RCE_API_KEY", "your_secret_key")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

app = FastAPI()
DOCKER_CLIENT = docker.from_env()
RCE_IMAGE_NAME = "custom-rce-kernel:latest"

# 2. Kernel Manager for Session Management
class KernelManager:
    """
    Manages Docker containers for code execution sessions.
    Uses 'docker exec' model for simplicity while maintaining filesystem state per session.
    """
    active_kernels = {} # Maps session_id to container object

    def get_or_create_container(self, session_id: str, force_refresh: bool = False):
        if not force_refresh and session_id in self.active_kernels:
            return self.active_kernels[session_id]

        if session_id in self.active_kernels:
            try:
                # Re-fetch or refresh container status
                container = self.active_kernels[session_id]
                # If we have an object, we can try to reload it to get fresh status
                try:
                    container.reload()
                except docker.errors.NotFound:
                    # If reload fails, it's gone
                    del self.active_kernels[session_id]
                    return self.start_new_container(session_id)

                if container.status == "running":
                    return container
                else:
                    # Restart if stopped
                    container.start()
                    return container
            except Exception:
                # Any other error, try to start fresh
                del self.active_kernels[session_id]

        return self.start_new_container(session_id)

    def start_new_container(self, session_id: str):
        # Create a unique volume for this session if needed (optional for simple exec)
        # For now, we rely on the container's internal filesystem persisting while it runs.
        
        try:
            container = DOCKER_CLIENT.containers.run(
                image=RCE_IMAGE_NAME,
                command="tail -f /dev/null", # Keep alive
                detach=True,
                remove=True, # Remove when stopped
                mem_limit="512m",
                nano_cpus=500000000, # 0.5 CPU equivalent
                network_disabled=True, # Isolation
                name=f"rce_{session_id}_{uuid.uuid4().hex[:6]}"
            )
            self.active_kernels[session_id] = container
            return container
        except Exception as e:
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Failed to start sandbox: {str(e)}")

    def execute_code(self, session_id: str, code: str):
        container = self.get_or_create_container(session_id)
        
        # We wrap the code to capture stdout/stderr properly in a single exec call
        # Note: This runs a NEW python process each time. Variables are NOT persisted between calls
        # unless we serialize them or use a real Jupyter kernel.
        # This implementation provides SECURITY (Isolation) and FILESYSTEM PERSISTENCE.
        
        # Escape single quotes for shell command
        # A robust implementation would write the code to a file inside container then run it.
        
        try:
            # 1. Write code to file inside container
            # (In a real implementation we would write the code content safely)
            
            cmd = ["python3", "-c", code]
            
            try:
                exec_result = container.exec_run(
                    cmd=cmd,
                    workdir="/usr/src/app"
                )
            except (docker.errors.APIError, docker.errors.NotFound):
                # Optimistic assumption failed: container might be stopped or gone
                # Recovery: Force refresh and retry once
                container = self.get_or_create_container(session_id, force_refresh=True)
                exec_result = container.exec_run(
                    cmd=cmd,
                    workdir="/usr/src/app"
                )
            
            return {
                "stdout": exec_result.output.decode("utf-8") if exec_result.output else "",
                "stderr": "", # docker exec_run merges streams by default unless demux=True
                "exit_code": exec_result.exit_code
            }
            
        except Exception as e:
            print(traceback.format_exc())
            return {"error": str(e)}

kernel_manager = KernelManager()

# 3. Request Schema
class CodeRequest(BaseModel):
    code: str
    session_id: str | None = None 

# 4. Code Execution Endpoint
@app.post("/run")
@app.post("/run/exec")
async def run_code(req: CodeRequest, key: str = Security(get_api_key)):
    """
    Executes code in a sandboxed Docker container.
    """
    session_id = req.session_id or str(uuid.uuid4())
    
    # Run in sandbox
    result = kernel_manager.execute_code(session_id, req.code)
    
    return result

@app.get("/health")
def health_check():
    return {"status": "ok", "mode": "docker-sandboxed"}