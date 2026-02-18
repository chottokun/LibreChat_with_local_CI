import io
import tarfile
import logging
import os
import uuid
import docker
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    def __init__(self):
        self.active_kernels = {} # Maps session_id to container object

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
            logger.exception("Failed to start sandbox for session %s", session_id)
            raise HTTPException(status_code=500, detail="Failed to start sandbox. Please contact an administrator.")

    def execute_code(self, session_id: str, code: str):
        container = self.get_or_create_container(session_id)
        
        # This implementation provides SECURITY (Isolation) and FILESYSTEM PERSISTENCE.
        # We write the code to a temporary file inside the container using 'put_archive'
        # to avoid shell escaping issues and command line length limits.
        
        code_filename = f"exec_{uuid.uuid4().hex}.py"
        container_path = f"/tmp/{code_filename}"
        
        try:
            # 1. Write code to file inside container
            def _run_with_retry(km, container, code_content, path, filename):
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                    code_bytes = code_content.encode('utf-8')
                    tar_info = tarfile.TarInfo(name=filename)
                    tar_info.size = len(code_bytes)
                    tar.addfile(tar_info, io.BytesIO(code_bytes))
                
                container.put_archive("/tmp", tar_stream.getvalue())
                
                return container.exec_run(
                    cmd=["python3", path],
                    workdir="/usr/src/app",
                    demux=True
                )

            try:
                exec_result = _run_with_retry(self, container, code, container_path, code_filename)
            except (docker.errors.APIError, docker.errors.NotFound):
                # Optimistic assumption failed: container might be stopped or gone
                # Recovery: Force refresh and retry once
                container = self.get_or_create_container(session_id, force_refresh=True)
                exec_result = _run_with_retry(self, container, code, container_path, code_filename)
            
            stdout, stderr = exec_result.output

            return {
                "stdout": stdout.decode("utf-8") if stdout else "",
                "stderr": stderr.decode("utf-8") if stderr else "",
                "exit_code": exec_result.exit_code
            }
            
        except Exception as e:
            logger.exception("Error executing code in session %s", session_id)
            return {"error": "An internal error occurred during code execution."}
        finally:
            # 3. Cleanup: remove the temporary file
            try:
                container.exec_run(cmd=["rm", container_path])
            except:
                pass

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