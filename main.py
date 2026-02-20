import io
import tarfile
import logging
import os
import uuid
import docker
from fastapi import FastAPI, HTTPException, Security, UploadFile, File, Form, Query
from fastapi.security import APIKeyHeader
import mimetypes
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Authentication Scheme
API_KEY = os.environ.get("LIBRECHAT_CODE_API_KEY", "your_secret_key")
# Use auto_error=False to allow fallback to query parameter
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(
    api_key_h: Optional[str] = Security(api_key_header),
    api_key_q: Optional[str] = Query(None, alias="api_key")
):
    key = api_key_h or api_key_q
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return key

app = FastAPI()
DOCKER_CLIENT = docker.from_env()
RCE_IMAGE_NAME = os.environ.get("RCE_IMAGE_NAME", "custom-rce-kernel:latest")

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
        # Configuration from environment variables
        mem_limit = os.environ.get("RCE_MEM_LIMIT", "512m")
        cpu_limit_nano = int(os.environ.get("RCE_CPU_LIMIT", "500000000")) # 0.5 CPU default
        network_enabled = os.environ.get("RCE_NETWORK_ENABLED", "false").lower() == "true"
        gpu_enabled = os.environ.get("RCE_GPU_ENABLED", "false").lower() == "true"
        
        device_requests = []
        if gpu_enabled:
            device_requests.append(
                docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])
            )

        try:
            container = DOCKER_CLIENT.containers.run(
                image=RCE_IMAGE_NAME,
                command="tail -f /dev/null", # Keep alive
                detach=True,
                remove=True, # Remove when stopped
                mem_limit=mem_limit,
                nano_cpus=cpu_limit_nano,
                network_disabled=not network_enabled,
                device_requests=device_requests,
                name=f"rce_{session_id}_{uuid.uuid4().hex[:6]}",
                working_dir="/usr/src/app"
            )
            # Ensure workspace exists
            container.exec_run(cmd=["mkdir", "-p", "/usr/src/app"])
            self.active_kernels[session_id] = container
            return container
        except Exception as e:
            logger.exception("Failed to start sandbox for session %s", session_id)
            raise HTTPException(status_code=500, detail="Failed to start sandbox. Please contact an administrator.")

    def upload_file(self, session_id: str, filename: str, content: bytes):
        container = self.get_or_create_container(session_id)
        # Sanitize filename to prevent path traversal
        safe_filename = os.path.basename(filename)
        if not safe_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            tar_info = tarfile.TarInfo(name=safe_filename)
            tar_info.size = len(content)
            tar.addfile(tar_info, io.BytesIO(content))
        
        container.put_archive("/usr/src/app", tar_stream.getvalue())
        logger.info("Uploaded file %s to session %s", safe_filename, session_id)

    def download_file(self, session_id: str, filename: str):
        container = self.get_or_create_container(session_id)
        # Sanitize filename to prevent path traversal
        safe_filename = os.path.basename(filename)
        if not safe_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        try:
            # get_archive returns a tuple: (stream, stat)
            bits, stat = container.get_archive(f"/usr/src/app/{safe_filename}")
            
            # Extract from tar bits
            tar_stream = io.BytesIO(b"".join(bits))
            with tarfile.open(fileobj=tar_stream, mode='r') as tar:
                # Use the first member from the tar archive for robustness
                members = tar.getmembers()
                if not members:
                    raise FileNotFoundError()
                f = tar.extractfile(members[0])
                if f:
                    return f.read(), stat.get('mtime', 0)
            raise FileNotFoundError()
        except Exception as e:
            logger.error("Failed to download file %s from session %s: %s", filename, session_id, e)
            raise HTTPException(status_code=404, detail="File not found")

    def list_files(self, session_id: str):
        container = self.get_or_create_container(session_id)
        # We list files and their sizes/mtimes if possible, or just names for now
        res = container.exec_run(cmd=["ls", "-1", "/usr/src/app"])
        if res.exit_code == 0:
            files = res.output.decode('utf-8').splitlines()
            return [f for f in files if f]
        return []

    def execute_code(self, session_id: str, code: str):
        """
        Executes code within the container.
        Returns a dictionary with stdout, stderr, and exit_code.
        Raises HTTPException for system errors.
        """
        container = self.get_or_create_container(session_id)
        
        # This implementation provides SECURITY (Isolation) and FILESYSTEM PERSISTENCE.
        # We write the code to a temporary file inside the container using 'put_archive'
        # to avoid shell escaping issues and command line length limits.
        
        code_filename = f"exec_{uuid.uuid4().hex}.py"
        container_path = f"/usr/src/app/{code_filename}"
        
        try:
            # 1. Write code to file inside container
            def _run_with_retry(km, container, code_content, path, filename):
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                    # Injected code to ensure /usr/src/app is in path
                    # although running from there should handle it.
                    code_bytes = code_content.encode('utf-8')
                    tar_info = tarfile.TarInfo(name=filename)
                    tar_info.size = len(code_bytes)
                    tar.addfile(tar_info, io.BytesIO(code_bytes))
                
                container.put_archive("/usr/src/app", tar_stream.getvalue())
                
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
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error executing code in session %s", session_id)
            raise HTTPException(status_code=500, detail="An internal error occurred during code execution.")
        finally:
            # 3. Cleanup: remove the temporary file
            try:
                container.exec_run(cmd=["rm", container_path])
            except:
                pass

kernel_manager = KernelManager()

# 3. Request/Response Schemas
class CodeRequest(BaseModel):
    code: str
    lang: Optional[str] = "py"
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    files: Optional[List[str]] = []

class CodeResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    output: Optional[str] = ""
    files: Optional[List[str]] = []

# 4. Endpoints
@app.post("/exec", response_model=CodeResponse)
@app.post("/run/exec", response_model=CodeResponse)
async def run_code(req: CodeRequest, key: str = Security(get_api_key)):
    """
    Executes code in a sandboxed Docker container.
    """
    session_id = req.session_id or str(uuid.uuid4())
    
    # Run in sandbox
    result = kernel_manager.execute_code(session_id, req.code)
    
    # List generated files (simplified: list all in workspace)
    # In a more advanced version, we would track changes.
    current_files = kernel_manager.list_files(session_id)
    
    return {
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "output": result["stdout"], # Simplified
        "files": current_files
    }

@app.post("/upload")
async def upload_files(
    entity_id: str = Form(...),
    files: List[UploadFile] = File(...),
    key: str = Security(get_api_key)
):
    """
    Uploads files to a specific session sandbox.
    """
    session_id = entity_id
    for file in files:
        content = await file.read()
        kernel_manager.upload_file(session_id, file.filename, content)
    
    return {"status": "ok", "files": [f.filename for f in files]}

@app.get("/files/{session_id}")
async def list_session_files(session_id: str, key: str = Security(get_api_key)):
    """
    Lists files in a session's sandbox.
    """
    files = kernel_manager.list_files(session_id)
    return {"files": files}

@app.get("/download")
@app.get("/run/download")
async def download_file_query(
    session_id: str = Query(...),
    filename: str = Query(...),
    key: str = Security(get_api_key)
):
    """
    Downloads a file from a session's sandbox using query parameters.
    """
    return await download_session_file(session_id, filename, key)

@app.get("/download/{session_id}/{filename}")
@app.get("/run/download/{session_id}/{filename}")
async def download_session_file(session_id: str, filename: str, key: str = Security(get_api_key)):
    """
    Downloads a file from a session's sandbox using path parameters.
    """
    content, mtime = kernel_manager.download_file(session_id, filename)

    # Guess MIME type
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Use inline for images and PDFs to allow them to be displayed in the chat interface
    disposition = "inline" if mime_type.startswith(("image/", "application/pdf")) else "attachment"

    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"{disposition}; filename={filename}"
        }
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "mode": "docker-sandboxed"}