import io
import tarfile
import logging
import os
import uuid
import docker
import threading
import time
import asyncio
import string
import random
from fastapi import FastAPI, HTTPException, Security, UploadFile, File, Form, Query
from fastapi.security import APIKeyHeader
from fastapi.responses import Response, FileResponse
import mimetypes
from pydantic import BaseModel
from typing import List, Optional, Dict
import shutil
import ast

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
API_KEY = os.environ.get("LIBRECHAT_CODE_API_KEY", "your_secret_key")
RCE_SESSION_TTL = int(os.environ.get("RCE_SESSION_TTL", "3600"))
RCE_MAX_SESSIONS = int(os.environ.get("RCE_MAX_SESSIONS", "100"))

# 1. Authentication Scheme
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

def wrap_code(code: str) -> str:
    """
    Wraps the last expression in print(repr(...)) if it's an expression.
    This mimics Jupyter/Notebook behavior where the last expression is automatically displayed.
    """
    try:
        tree = ast.parse(code)
        if not tree.body:
            return code

        last_node = tree.body[-1]
        if isinstance(last_node, ast.Expr):
            # Wrap the expression in:
            # __last_res__ = <expression>
            # if __last_res__ is not None: print(repr(__last_res__))
            # This mimics Jupyter/Notebook behavior.

            # Create: __last_res__ = <last_node.value>
            assign_node = ast.Assign(
                targets=[ast.Name(id='__last_res__', ctx=ast.Store())],
                value=last_node.value
            )

            # Create: if __last_res__ is not None: print(repr(__last_res__))
            if_node = ast.If(
                test=ast.Compare(
                    left=ast.Name(id='__last_res__', ctx=ast.Load()),
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=None)]
                ),
                body=[
                    ast.Expr(
                        value=ast.Call(
                            func=ast.Name(id='print', ctx=ast.Load()),
                            args=[
                                ast.Call(
                                    func=ast.Name(id='repr', ctx=ast.Load()),
                                    args=[ast.Name(id='__last_res__', ctx=ast.Load())],
                                    keywords=[]
                                )
                            ],
                            keywords=[]
                        )
                    )
                ],
                orelse=[]
            )

            tree.body[-1] = assign_node
            tree.body.append(if_node)
            ast.fix_missing_locations(tree)
            return ast.unparse(tree)
    except Exception:
        # If parsing fails (e.g. syntax error), return original code and let it fail during execution
        return code
    return code

app = FastAPI()

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

DOCKER_CLIENT = docker.from_env()
RCE_IMAGE_NAME = os.environ.get("RCE_IMAGE_NAME", "custom-rce-kernel:latest")

# Nanoid-compatible ID generation (21 chars, [A-Za-z0-9_-])
_NANOID_ALPHABET = string.ascii_letters + string.digits + '_-'
def generate_nanoid(size: int = 21) -> str:
    return ''.join(random.choices(_NANOID_ALPHABET, k=size))

# Mapping: nanoid_session_id -> uuid_session_id and nanoid_file_id -> filename
_nanoid_to_session: Dict[str, str] = {}
_session_to_nanoid: Dict[str, str] = {}
_file_id_map: Dict[str, Dict[str, str]] = {}  # {nanoid_session_id: {nanoid_file_id: filename}}

# 2. Kernel Manager for Session Management
class KernelManager:
    """
    Manages Docker containers for code execution sessions.
    Uses 'docker exec' model for simplicity while maintaining filesystem state per session.
    """
    def __init__(self):
        self.active_kernels = {} # Maps session_id to dict with container and last_accessed
        self.lock = threading.Lock()

    def get_or_create_container(self, session_id: str, force_refresh: bool = False):
        with self.lock:
            if not force_refresh and session_id in self.active_kernels:
                self.active_kernels[session_id]["last_accessed"] = time.time()
                return self.active_kernels[session_id]["container"]

            if session_id in self.active_kernels:
                try:
                    # Re-fetch or refresh container status
                    container = self.active_kernels[session_id]["container"]
                    # If we have an object, we can try to reload it to get fresh status
                    try:
                        container.reload()
                    except docker.errors.NotFound:
                        # If reload fails, it's gone
                        del self.active_kernels[session_id]
                        return self.start_new_container_unlocked(session_id)

                    if container.status == "running":
                        self.active_kernels[session_id]["last_accessed"] = time.time()
                        return container
                    else:
                        # Restart if stopped
                        container.start()
                        self.active_kernels[session_id]["last_accessed"] = time.time()
                        return container
                except Exception:
                    # Any other error, try to start fresh
                    del self.active_kernels[session_id]

            return self.start_new_container_unlocked(session_id)

    def start_new_container(self, session_id: str):
        with self.lock:
            return self.start_new_container_unlocked(session_id)

    def start_new_container_unlocked(self, session_id: str):
        # Enforce max sessions
        if len(self.active_kernels) >= RCE_MAX_SESSIONS:
            logger.warning("Max sessions reached: %d", RCE_MAX_SESSIONS)
            raise HTTPException(status_code=503, detail="Server is at capacity. Please try again later.")

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
                working_dir="/usr/src/app",
                labels={
                    "managed_by": "librechat-rce",
                    "session_id": session_id
                },
                environment={"PYTHONUNBUFFERED": "1"}
            )
            # Ensure workspace exists
            container.exec_run(cmd=["mkdir", "-p", "/usr/src/app"])
            self.active_kernels[session_id] = {
                "container": container,
                "last_accessed": time.time()
            }
            return container
        except Exception as e:
            logger.exception("Failed to start sandbox for session %s", session_id)
            raise HTTPException(status_code=500, detail="Failed to start sandbox. Please contact an administrator.")

    def recover_containers(self):
        """Scans Docker for existing containers managed by this API and re-adopts them."""
        logger.info("Scanning for existing containers to recover...")
        try:
            containers = DOCKER_CLIENT.containers.list(
                all=True,
                filters={"label": "managed_by=librechat-rce"}
            )
            with self.lock:
                for container in containers:
                    session_id = container.labels.get("session_id")
                    if session_id and session_id not in self.active_kernels:
                        try:
                            # We don't auto-start here to avoid load spikes.
                            # They will be started on first request.
                            self.active_kernels[session_id] = {
                                "container": container,
                                "last_accessed": time.time()
                            }
                            logger.info("Recovered session %s from container %s", session_id, container.id)
                        except Exception as e:
                            logger.error("Failed to recover container %s: %s", container.id, e)
        except Exception as e:
            logger.error("Error during container recovery: %s", e)

    def cleanup_sessions(self):
        """Stops and removes containers that have exceeded the TTL."""
        now = time.time()
        to_delete = []
        with self.lock:
            for session_id, data in self.active_kernels.items():
                if now - data["last_accessed"] > RCE_SESSION_TTL:
                    to_delete.append(session_id)

        for session_id in to_delete:
            logger.info("Cleaning up idle session: %s", session_id)
            try:
                with self.lock:
                    data = self.active_kernels.pop(session_id, None)
                if data:
                    container = data["container"]
                    container.stop(timeout=5)
                    # Since remove=True was used, it should be gone now.
            except Exception as e:
                logger.error("Error cleaning up session %s: %s", session_id, e)

    async def cleanup_loop(self):
        """Background loop for periodic cleanup."""
        while True:
            try:
                # Run cleanup in a separate thread to avoid blocking the event loop
                await asyncio.to_thread(self.cleanup_sessions)
            except Exception as e:
                logger.error("Error in cleanup loop: %s", e)
            await asyncio.sleep(60) # Run every minute

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
            # 1. Apply code wrapping for expression-only support
            wrapped_code = wrap_code(code)

            # 2. Write code to file inside container
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
                exec_result = _run_with_retry(self, container, wrapped_code, container_path, code_filename)
            except (docker.errors.APIError, docker.errors.NotFound):
                # Optimistic assumption failed: container might be stopped or gone
                # Recovery: Force refresh and retry once
                container = self.get_or_create_container(session_id, force_refresh=True)
                exec_result = _run_with_retry(self, container, wrapped_code, container_path, code_filename)
            
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

class FileInfo(BaseModel):
    id: str
    name: str
    url: str
    type: str

class CodeResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    output: Optional[str] = ""
    session_id: Optional[str] = None
    files: Optional[List[FileInfo]] = []

# 4. Endpoints
@app.on_event("startup")
async def startup_event():
    # Recover existing containers
    kernel_manager.recover_containers()
    # Start cleanup background task
    asyncio.create_task(kernel_manager.cleanup_loop())

@app.post("/exec", response_model=CodeResponse)
@app.post("/run/exec", response_model=CodeResponse)
async def run_code(req: CodeRequest, key: str = Security(get_api_key)):
    """
    Executes code in a sandboxed Docker container.
    """
    session_id = req.session_id or str(uuid.uuid4())
    
    # Generate or reuse a nanoid-compatible session ID for LibreChat
    if session_id not in _session_to_nanoid:
        nanoid_session = generate_nanoid()
        _session_to_nanoid[session_id] = nanoid_session
        _nanoid_to_session[nanoid_session] = session_id
    nanoid_session = _session_to_nanoid[session_id]
    
    # Run in sandbox
    result = kernel_manager.execute_code(session_id, req.code)
    
    # List generated files and format them for LibreChat native ingestion
    current_files = kernel_manager.list_files(session_id)
    structured_files = []
    
    # Initialize file mapping for this session
    if nanoid_session not in _file_id_map:
        _file_id_map[nanoid_session] = {}
    
    for f in current_files:
        mime_type, _ = mimetypes.guess_type(f)
        # Generate or reuse nanoid for this file
        existing_ids = {v: k for k, v in _file_id_map[nanoid_session].items()}
        if f in existing_ids:
            nanoid_file = existing_ids[f]
        else:
            nanoid_file = generate_nanoid()
            _file_id_map[nanoid_session][nanoid_file] = f
        structured_files.append({
            "id": nanoid_file,
            "name": f,
            "url": f"/api/files/code/download/{nanoid_session}/{nanoid_file}",
            "type": mime_type or "application/octet-stream"
        })
    
    return {
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "output": result["stdout"], # Simplified
        "session_id": nanoid_session,
        "files": structured_files
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

@app.get("/api/files/code/download/{session_id}/{filename}")
@app.get("/download/{session_id}/{filename}")
@app.get("/run/download/{session_id}/{filename}")
async def download_session_file(session_id: str, filename: str, key: Optional[str] = Security(get_api_key)):
    """
    Downloads a file from a session's sandbox using path parameters.
    Supports nanoid-format IDs (used by LibreChat) and direct session_id/filename.
    Uses FileResponse to ensure perfect streaming header compatibility with LibreChat's Axios proxy.
    """
    # Resolve nanoid session ID to real UUID session ID
    real_session_id = _nanoid_to_session.get(session_id, session_id)
    
    # Resolve nanoid file ID to real filename
    real_filename = filename
    if session_id in _file_id_map and filename in _file_id_map[session_id]:
        real_filename = _file_id_map[session_id][filename]
    
    content, mtime = kernel_manager.download_file(real_session_id, real_filename)

    # Guess MIME type
    mime_type, _ = mimetypes.guess_type(real_filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Use inline for images and PDFs to allow them to be displayed in the chat interface
    disposition = "inline" if mime_type.startswith(("image/", "application/pdf")) else "attachment"
    
    # Save the file to /tmp so FastAPI can stream it natively via FileResponse
    import os
    tmp_filepath = f"/tmp/{real_session_id}_{real_filename}"
    with open(tmp_filepath, "wb") as f:
        f.write(content)

    return FileResponse(
        path=tmp_filepath,
        filename=real_filename,
        media_type=mime_type,
        content_disposition_type=disposition
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "mode": "docker-sandboxed"}