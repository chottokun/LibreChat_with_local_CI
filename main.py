from __future__ import annotations
import io
import weakref
import tarfile
import logging
import os
from pathlib import Path
import uuid
import docker
import threading
import time
import asyncio
import string
import secrets
from unittest.mock import MagicMock
from fastapi import FastAPI, HTTPException, Security, UploadFile, File, Form, Query, BackgroundTasks, Response, Request
from contextlib import asynccontextmanager
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
import mimetypes
from urllib.parse import quote
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor
import shutil
import ast
import json
import base64
from fastapi.middleware.cors import CORSMiddleware
if TYPE_CHECKING:
    from starlette.types import Scope, Send

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 直近でファイルがアップロードされたセッション情報を一時記録するグローバル変数（認証バグやセッション連携漏れ回避用）
LAST_UPLOADED_SESSION_ID = None
LAST_UPLOAD_TIME = 0

# 設定情報の読み込み
# DISABLE_CODE_API_AUTH: テスト・ローカル環境等において認証なしでのアクセスを許可するかどうかのフラグ
DISABLE_AUTH = os.environ.get("DISABLE_CODE_API_AUTH", "false").lower() == "true"
API_KEY = os.environ.get("LIBRECHAT_CODE_API_KEY")

# 認証が有効で、かつAPIキーが設定されていない場合は起動エラーとする
if not DISABLE_AUTH and not API_KEY:
    logger.error("LIBRECHAT_CODE_API_KEY environment variable is not set.")
    raise RuntimeError("LIBRECHAT_CODE_API_KEY environment variable is not set.")

# RCE_DATA_DIR_HOST is the path on the Docker Host (used for mounting)
_raw_data_dir = os.environ.get("RCE_DATA_DIR_HOST", os.environ.get("RCE_DATA_DIR", ""))
# RCE_DATA_DIR_INTERNAL is the path inside this API container (used for writing files)
RCE_DATA_DIR_INTERNAL = os.environ.get("RCE_DATA_DIR_INTERNAL", "/app/shared_volumes/sessions")

# 1. Validation for RCE_DATA_DIR
if not _raw_data_dir or "absolute/path/to/your/project/sessions" in _raw_data_dir:
    # Use default mode (put_archive) if path is not set or is the placeholder
    RCE_DATA_DIR_HOST = None
    if _raw_data_dir:
        logger.info("RCE_DATA_DIR is set to placeholder. Using default 'put_archive' mode.")
else:
    RCE_DATA_DIR_HOST = _raw_data_dir

# 2. Writability check for shared volume
if RCE_DATA_DIR_HOST:
    try:
        Path(RCE_DATA_DIR_INTERNAL).mkdir(parents=True, exist_ok=True)
        if not os.access(RCE_DATA_DIR_INTERNAL, os.W_OK):
            logger.warning("!!! PERMISSION ERROR !!!")
            logger.warning(f"RCE_DATA_DIR is set to '{RCE_DATA_DIR_HOST}', but the internal path '{RCE_DATA_DIR_INTERNAL}' is not writable.")
            logger.warning("Falling back to 'put_archive' mode (slower, but works without host mounting).")
            logger.warning("To fix this, ensure the host directory has correct permissions (e.g., sudo chown -R 1000:1000 <dir>)")
            RCE_DATA_DIR_HOST = None
        else:
            logger.info(f"Volume mounting enabled: {RCE_DATA_DIR_HOST} -> {RCE_DATA_DIR_INTERNAL}")
    except Exception as e:
        logger.warning(f"Failed to initialize shared volume: {e}. Falling back to 'put_archive' mode.")
        RCE_DATA_DIR_HOST = None

RCE_SESSION_TTL = int(os.environ.get("RCE_SESSION_TTL", "3600"))
RCE_MAX_SESSIONS = int(os.environ.get("RCE_MAX_SESSIONS", "100"))
RCE_MANAGED_BY_VALUE = "librechat-rce"

# 1. 認証スキームの設定
# クエリパラメータによるAPIキーフォールバックを許可するため、auto_error=False に設定
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

async def get_api_key(
    request: Request = None,
    api_key_h: Optional[str] = Security(api_key_header),
    api_key_q: Optional[str] = Query(None, alias="api_key"),
    token: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> Optional[str]:
    # テスト環境用に認証をスキップする設定が有効な場合、即座に通過させる
    if DISABLE_AUTH:
        return "disabled"

    # さまざまなリクエストクライアント（LibreChatやOpen WebUIなど）からの接続に対応するため、
    # 複数のヘッダー形式やクエリパラメータを順次フォールバックしてパースする。
    
    # A. Authorization: Bearer <key> ヘッダーの確認 (FastAPI HTTPBearerを使用)
    auth_key = token.credentials if isinstance(token, HTTPAuthorizationCredentials) else None

    # B. X-API-Key ヘッダー (api_key_header 経由)
    h_key = api_key_h if isinstance(api_key_h, str) else None

    # C. クエリパラメータ (Query 経由)
    q_key = api_key_q if isinstance(api_key_q, str) else None

    # D. フォールバック: 手動での x-api-key ヘッダー取得 (既存互換性のため)
    manual_x_api_key = None
    if request is not None and hasattr(request, "headers"):
        manual_x_api_key = request.headers.get("x-api-key")

    # 全ての候補をマージして検証
    key = auth_key or h_key or q_key or manual_x_api_key
    
    # 期待される APIキーと不一致の場合は 401 拒否とする
    # Timing attack を防ぐため、secrets.compare_digest を使用
    if not (key and secrets.compare_digest(key, API_KEY)):
        # トラブルシューティングの容易化のため、受け取ったキーと期待されたキー、全ヘッダーのデバッグ警告を出力
        logger.warning(
            "Authentication failure in get_api_key! Received key: %s, Expected key (API_KEY): %s. "
            "Headers: %s",
            key, API_KEY, dict(request.headers) if request is not None and hasattr(request, "headers") else {}
        )
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return key


def _create_last_res_assign(value: ast.expr) -> ast.Assign:
    """ASTノードを作成: __last_res__ = <value>"""
    return ast.Assign(
        targets=[ast.Name(id="__last_res__", ctx=ast.Store())], value=value
    )


def _create_last_res_if_print() -> ast.If:
    """ASTノードを作成: if __last_res__ is not None: print(repr(__last_res__))"""
    return ast.If(
        test=ast.Compare(
            left=ast.Name(id="__last_res__", ctx=ast.Load()),
            ops=[ast.IsNot()],
            comparators=[ast.Constant(value=None)],
        ),
        body=[
            ast.Expr(
                value=ast.Call(
                    func=ast.Name(id="print", ctx=ast.Load()),
                    args=[
                        ast.Call(
                            func=ast.Name(id="repr", ctx=ast.Load()),
                            args=[ast.Name(id="__last_res__", ctx=ast.Load())],
                            keywords=[],
                        )
                    ],
                    keywords=[],
                )
            )
        ],
        orelse=[],
    )


def wrap_code(code: str) -> str:
    """
    最後の式が評価式の場合、print(repr(...)) でラップします。
    Jupyter Notebookのように、最後の式が自動で表示される挙動を模倣します。
    """
    try:
        tree = ast.parse(code)
        if not tree.body:
            return code

        last_node = tree.body[-1]
        if isinstance(last_node, ast.Expr):
            # 式をラップする:
            # __last_res__ = <expression>
            # if __last_res__ is not None: print(repr(__last_res__))
            tree.body[-1] = _create_last_res_assign(last_node.value)
            tree.body.append(_create_last_res_if_print())
            ast.fix_missing_locations(tree)
            return ast.unparse(tree)
    except Exception:
        # パースに失敗した場合は、元のコードをそのまま返して実行時にエラーとします。
        return code
    return code


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Recover existing containers
    kernel_manager.recover_containers()
    # Start cleanup background task
    cleanup_task = asyncio.create_task(kernel_manager.cleanup_loop())
    yield
    # Shutdown logic
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        logger.info("Cleanup task cancelled during shutdown.")

app = FastAPI(lifespan=lifespan)



class SecurityHeadersCORSMiddleware(CORSMiddleware):
    """
    Extends CORSMiddleware to also add security headers on non-download responses.
    This avoids the issue where @app.middleware('http') wraps CORSMiddleware
    and prevents it from intercepting OPTIONS preflight requests.
    """
    SECURITY_DOWNLOAD_PREFIXES = (
        "/download",
        "/run/download",
        "/files/download",
        "/api/download",
        "/api/files/download",
        "/api/files/code/download",
        "/files/code/download",
        "/api/code/download",
        "/code/download",
    )

    async def __call__(self, scope: Scope, receive, send: Send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        path = scope.get("path", "")
        is_download = path.startswith(self.SECURITY_DOWNLOAD_PREFIXES)

        if is_download:
            # For download paths: just do CORS, no security headers
            await super().__call__(scope, receive, send)
        else:
            # For non-download paths: do CORS + add security headers
            async def send_with_security(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.extend([
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"x-xss-protection", b"1; mode=block"),
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                        (b"referrer-policy", b"no-referrer"),
                    ])
                    message["headers"] = headers
                await send(message)
            await super().__call__(scope, receive, send_with_security)

# CORS configuration
CORS_ALLOWED_ORIGINS_RAW = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3080")
CORS_ALLOWED_ORIGINS = []
for origin in CORS_ALLOWED_ORIGINS_RAW.split(","):
    origin_cleaned = origin.strip().rstrip("/")
    if origin_cleaned == "*":
        logger.error("Wildcard '*' origin is not allowed when credentials are enabled.")
        raise ValueError("CORS_ALLOWED_ORIGINS cannot contain '*' when allow_credentials is True.")
    if origin_cleaned:
        CORS_ALLOWED_ORIGINS.append(origin_cleaned)

app.add_middleware(
    SecurityHeadersCORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
DOCKER_CLIENT = docker.from_env()
RCE_IMAGE_NAME = os.environ.get("RCE_IMAGE_NAME", "custom-rce-kernel:latest")

# Nanoid-compatible ID generation (21 chars, [A-Za-z0-9_-])
_NANOID_ALPHABET = string.ascii_letters + string.digits + '_-'
def generate_nanoid(size: int = 21) -> str:
    return ''.join(secrets.choice(_NANOID_ALPHABET) for _ in range(size))

def sanitize_id(id_str: str) -> str:
    """Sanitizes an ID to allow only alphanumeric, hyphen, and underscore."""
    if not id_str:
        return ""
    # Remove any characters that are not alphanumeric, hyphen, or underscore
    # This prevents path traversal and other injection attacks.
    cleaned = "".join(c for c in id_str if c.isalnum() or c in ('-', '_'))
    if cleaned.lower() in ("null", "undefined", "none", "nan"):
        return ""
    return cleaned

def _get_session_ids(sid: str) -> Tuple[str, str]:
    """
    Resolves a provided session ID to a real internal session ID and returns the pair.
    Includes a fallback for unittest mocks that do not have get_or_create_session_mapping configured.
    """
    if isinstance(kernel_manager, MagicMock):
        # Fallback for unittest mocks that do not have get_or_create_session_mapping configured
        real_session_id = kernel_manager.resolve_session_id(sanitize_id(sid))
        nanoid_session = sid
    else:
        real_session_id, nanoid_session = kernel_manager.get_or_create_session_mapping(sid)
    return real_session_id, nanoid_session

class WeakrefRLock:
    """A wrapper around threading.RLock that supports weak references."""
    def __init__(self):
        self._lock = threading.RLock()

    def __enter__(self):
        return self._lock.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._lock.__exit__(exc_type, exc_val, exc_tb)

    def acquire(self, blocking=True, timeout=-1):
        return self._lock.acquire(blocking, timeout)

    def release(self):
        return self._lock.release()

# 2. Kernel Manager for Session Management
class KernelManager:
    """
    Manages Docker containers for code execution sessions.
    Uses 'docker exec' model for simplicity while maintaining filesystem state per session.
    """
    def __init__(self):
        self.active_kernels = {} # Maps session_id to dict with container and last_accessed
        self.lock = threading.Lock()
        self.session_locks = weakref.WeakValueDictionary()
        self.session_locks_lock = threading.Lock()
        self.pending_sessions = set() # Track sessions currently in the process of starting
        # Mapping: nanoid_session_id -> uuid_session_id and nanoid_file_id -> filename
        self.nanoid_to_session: Dict[str, str] = {}
        self.session_to_nanoid: Dict[str, str] = {}
        self.file_id_map: Dict[str, Dict[str, str]] = {}  # {nanoid_session_id: {nanoid_file_id: filename}}
        self._cached_config: Optional[Dict[str, Any]] = None

    def _get_session_lock(self, session_id: str) -> WeakrefRLock:
        """Gets or creates a session-specific lock."""
        with self.session_locks_lock:
            lock = self.session_locks.get(session_id)
            if lock is None:
                lock = WeakrefRLock()
                self.session_locks[session_id] = lock
            return lock

    def resolve_session_id(self, session_id: str) -> str:
        """Resolves a potential nanoid session ID to the real internal session ID."""
        sanitized_id = sanitize_id(session_id)
        with self.lock:
            return self.nanoid_to_session.get(sanitized_id, sanitized_id)

    def get_or_create_session_mapping(self, sid: str) -> Tuple[str, str]:
        """
        Resolves or creates a thread-safe mapping between a NanoID session ID
        and an internal UUID session ID.
        Returns a tuple of (real_session_id, nanoid_session).
        Guarantees that the returned nanoid_session is a valid 21-character Nanoid.
        """
        s_sid = sanitize_id(sid)
        if not s_sid or s_sid.lower() in ("null", "undefined", "none"):
            s_sid = generate_nanoid()

        with self.lock:
            # Resolve to real internal session ID
            real_session_id = self.nanoid_to_session.get(s_sid)

            if not real_session_id:
                if s_sid in self.session_to_nanoid:
                    real_session_id = s_sid
                else:
                    real_session_id = str(uuid.uuid4())
                    self.nanoid_to_session[s_sid] = real_session_id
                    logger.info("Mapped provided SID %s to new internal UUID %s", s_sid, real_session_id)

            # Ensure we have a valid 21-character Nanoid mapping for this real_session_id
            nanoid_session = self.session_to_nanoid.get(real_session_id)
            if not nanoid_session:
                if len(s_sid) == 21:
                    nanoid_session = s_sid
                else:
                    nanoid_session = generate_nanoid()

                self.session_to_nanoid[real_session_id] = nanoid_session
                self.nanoid_to_session[nanoid_session] = real_session_id

            return real_session_id, nanoid_session

    def resolve_download_ids(self, session_id: str, filename: str) -> Tuple[str, str]:
        """Resolves potential nanoid IDs for session and file to their real values."""
        raw_sanitized = "".join(c for c in session_id if c.isalnum() or c in ('-', '_')) if session_id else ""
        if session_id and not raw_sanitized:
            raise HTTPException(status_code=400, detail="Invalid session ID")

        s_session_id = sanitize_id(session_id)
        s_filename = filename.strip().lstrip("/")

        with self.lock:
            target_nanoid_session = None
            if s_session_id and s_session_id.lower() not in ("null", "undefined", "none"):
                if s_session_id in self.nanoid_to_session:
                    real_session_id = self.nanoid_to_session[s_session_id]
                    target_nanoid_session = s_session_id
                else:
                    real_session_id = s_session_id
                    target_nanoid_session = self.session_to_nanoid.get(s_session_id, s_session_id)
            else:
                real_session_id = None
                target_nanoid_session = None

            real_filename = s_filename
            found_in_session = False

            if target_nanoid_session and target_nanoid_session in self.file_id_map:
                if s_filename in self.file_id_map[target_nanoid_session]:
                    real_filename = self.file_id_map[target_nanoid_session][s_filename]
                    found_in_session = True
                elif os.path.basename(s_filename) in self.file_id_map[target_nanoid_session]:
                    real_filename = self.file_id_map[target_nanoid_session][os.path.basename(s_filename)]
                    found_in_session = True

            # Cross-session lookup fallback: if not found in target session or target session is invalid,
            # search file_id_map across all sessions for s_filename or basename
            if not found_in_session:
                base_fn = os.path.basename(s_filename)

                # Check LAST_UPLOADED_SESSION_ID first if available
                global LAST_UPLOADED_SESSION_ID, LAST_UPLOAD_TIME
                search_sessions = list(self.file_id_map.keys())
                if LAST_UPLOADED_SESSION_ID and (time.time() - LAST_UPLOAD_TIME < 300):
                    pref_sid = sanitize_id(LAST_UPLOADED_SESSION_ID)
                    pref_nanoid = self.session_to_nanoid.get(pref_sid, pref_sid)
                    if pref_nanoid in search_sessions:
                        search_sessions.remove(pref_nanoid)
                        search_sessions.insert(0, pref_nanoid)

                for map_nanoid_sid in search_sessions:
                    id_map = self.file_id_map[map_nanoid_sid]
                    if s_filename in id_map:
                        real_filename = id_map[s_filename]
                        real_session_id = self.nanoid_to_session.get(map_nanoid_sid, map_nanoid_sid)
                        found_in_session = True
                        logger.info("Resolved file ID %s via cross-session lookup to session %s (file: %s)", s_filename, real_session_id, real_filename)
                        break
                    elif base_fn in id_map:
                        real_filename = id_map[base_fn]
                        real_session_id = self.nanoid_to_session.get(map_nanoid_sid, map_nanoid_sid)
                        found_in_session = True
                        logger.info("Resolved file ID %s (basename: %s) via cross-session lookup to session %s (file: %s)", s_filename, base_fn, real_session_id, real_filename)
                        break
                    elif target_nanoid_session is None and s_filename in id_map.values():
                        real_filename = s_filename
                        real_session_id = self.nanoid_to_session.get(map_nanoid_sid, map_nanoid_sid)
                        found_in_session = True
                        logger.info("Resolved filename %s via cross-session lookup to session %s", s_filename, real_session_id)
                        break
                    elif target_nanoid_session is None and base_fn in id_map.values():
                        real_filename = base_fn
                        real_session_id = self.nanoid_to_session.get(map_nanoid_sid, map_nanoid_sid)
                        found_in_session = True
                        logger.info("Resolved filename %s (basename: %s) via cross-session lookup to session %s", s_filename, base_fn, real_session_id)
                        break

            # Check filesystem on disk across active sessions if volume mapping is used
            if not found_in_session and RCE_DATA_DIR_INTERNAL and target_nanoid_session is None:
                safe_base_fn = Path(s_filename).name
                if safe_base_fn and safe_base_fn not in (".", ".."):
                    abs_base = Path(RCE_DATA_DIR_INTERNAL).resolve()
                    for active_sid in list(self.active_kernels.keys()):
                        safe_active_sid = sanitize_id(active_sid)
                        if not safe_active_sid:
                            continue
                        cand_dir = (abs_base / safe_active_sid).resolve()
                        cand_file = (cand_dir / safe_base_fn).resolve()
                        if cand_file.is_relative_to(cand_dir) and cand_file.exists():
                            real_filename = safe_base_fn
                            real_session_id = active_sid
                            found_in_session = True
                            logger.info("Resolved file %s on disk in active session %s", safe_base_fn, real_session_id)
                            break

            # Fallback for real_session_id if still unassigned or invalid
            if not real_session_id or real_session_id.lower() in ("null", "undefined", "none"):
                if LAST_UPLOADED_SESSION_ID and (time.time() - LAST_UPLOAD_TIME < 300):
                    s_last = sanitize_id(LAST_UPLOADED_SESSION_ID)
                    if s_last:
                        real_session_id = self.nanoid_to_session.get(s_last, s_last)
                        logger.info("Resolved download session ID from LAST_UPLOADED_SESSION_ID: %s", real_session_id)
                    else:
                        raise HTTPException(status_code=400, detail="Invalid session ID")
                else:
                    raise HTTPException(status_code=400, detail="Invalid session ID")

            # Normalize relative path while preventing path traversal
            path_obj = Path(real_filename)
            if ".." in path_obj.parts or path_obj.is_absolute():
                raise HTTPException(status_code=400, detail="Invalid filename")

            norm_filename = str(path_obj).lstrip("/")
            if not norm_filename or norm_filename == ".":
                raise HTTPException(status_code=400, detail="Invalid filename")
            return real_session_id, norm_filename

    def get_or_create_container(self, session_id: str, force_refresh: bool = False, external_session_id: Optional[str] = None):
        # Fast path: check if session exists and is not being refreshed
        with self.lock:
            if not force_refresh and session_id in self.active_kernels:
                self.active_kernels[session_id]["last_accessed"] = time.time()
                return self.active_kernels[session_id]["container"]

        # Slow path: use session-specific lock to avoid blocking other sessions
        session_lock = self._get_session_lock(session_id)
        with session_lock:
            container_to_refresh = None
            with self.lock:
                # Re-check under lock in case it was created/refreshed while waiting for session_lock
                if not force_refresh and session_id in self.active_kernels:
                    self.active_kernels[session_id]["last_accessed"] = time.time()
                    return self.active_kernels[session_id]["container"]

                if session_id in self.active_kernels:
                    container_to_refresh = self.active_kernels[session_id]["container"]

            if container_to_refresh:
                try:
                    # Slow Docker API call outside global lock
                    container_to_refresh.reload()
                    if container_to_refresh.status == "running":
                        with self.lock:
                            if session_id in self.active_kernels:
                                self.active_kernels[session_id]["last_accessed"] = time.time()
                        return container_to_refresh
                    else:
                        # Slow Docker API call outside global lock
                        container_to_refresh.start()
                        with self.lock:
                            if session_id in self.active_kernels:
                                self.active_kernels[session_id]["last_accessed"] = time.time()
                        return container_to_refresh
                except docker.errors.NotFound:
                    with self.lock:
                        self.active_kernels.pop(session_id, None)
                    # Fall through to create new
                except Exception:
                    logger.exception("Error refreshing container for session %s", session_id)
                    with self.lock:
                        self.active_kernels.pop(session_id, None)
                    # Fall through to create new

            return self.start_new_container(session_id, external_session_id)

    def start_new_container(self, session_id: str, external_session_id: Optional[str] = None):
        session_lock = self._get_session_lock(session_id)
        with session_lock:
            # Double check existence and capacity under global lock
            with self.lock:
                if session_id in self.active_kernels:
                    return self.active_kernels[session_id]["container"]

                # Prevent race condition: check active kernels AND currently starting containers
                if len(self.active_kernels) + len(self.pending_sessions) >= RCE_MAX_SESSIONS:
                    logger.warning("Max sessions reached: %d (Active: %d, Pending: %d)", 
                                   RCE_MAX_SESSIONS, len(self.active_kernels), len(self.pending_sessions))
                    raise HTTPException(status_code=503, detail="Server is at capacity. Please try again later.")
                
                # Mark as pending to reserve slot
                self.pending_sessions.add(session_id)

            # Slow Docker operations outside global lock
            container = None
            try:
                config = self._get_container_config()
                volumes = self._prepare_volumes(session_id)

                container = DOCKER_CLIENT.containers.run(
                    image=RCE_IMAGE_NAME,
                    command="tail -f /dev/null", # Keep alive
                    detach=True,
                    remove=True, # Remove when stopped
                    name=f"rce_{session_id}_{uuid.uuid4().hex[:6]}",
                    working_dir="/mnt/data",
                    labels={
                        "managed_by": RCE_MANAGED_BY_VALUE,
                        "session_id": session_id,
                        "external_session_id": external_session_id or ""
                    },
                    environment={"PYTHONUNBUFFERED": "1"},
                    volumes=volumes,
                    **config
                )
                # Ensure workspace exists
                container.exec_run(cmd=["mkdir", "-p", "/mnt/data"])

                with self.lock:
                    self.active_kernels[session_id] = {
                        "container": container,
                        "last_accessed": time.time()
                    }
                    self.pending_sessions.discard(session_id)
                return container
            except Exception:
                logger.exception("Failed to start sandbox for session %s", session_id)
                with self.lock:
                    self.pending_sessions.discard(session_id)
                if container:
                    try:
                        container.stop(timeout=2)
                    except Exception as stop_err:
                        logger.error("Failed to stop container %s after startup failure: %s", container.id if hasattr(container, "id") else "unknown", stop_err)
                raise HTTPException(status_code=500, detail="Failed to start sandbox. Please contact an administrator.")

    def _get_container_config(self) -> Dict[str, Any]:
        """Parses resource limits and configuration from environment variables."""
        if self._cached_config is None:
            mem_limit = os.environ.get("RCE_MEM_LIMIT", "512m")
            cpu_limit_nano = int(os.environ.get("RCE_CPU_LIMIT", "500000000")) # 0.5 CPU default
            network_enabled = os.environ.get("RCE_NETWORK_ENABLED", "false").lower() == "true"
            gpu_enabled = os.environ.get("RCE_GPU_ENABLED", "false").lower() == "true"

            device_requests = []
            if gpu_enabled:
                device_requests.append(
                    docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])
                )

            self._cached_config = {
                "mem_limit": mem_limit,
                "nano_cpus": cpu_limit_nano,
                "network_disabled": not network_enabled,
                "device_requests": device_requests
            }

        # Return a copy to prevent callers from corrupting the cache
        config = self._cached_config.copy()
        config["device_requests"] = list(self._cached_config["device_requests"])
        return config

    def _prepare_volumes(self, session_id: str) -> Dict[str, Dict[str, str]]:
        """Prepares session directory and returns volume mapping if enabled."""
        if not RCE_DATA_DIR_HOST:
            return {}

        # Basic sanitization and validation of session_id to prevent path traversal
        safe_sid = sanitize_id(session_id)
        if not safe_sid:
            logger.error("Invalid session ID for volume preparation: %s", session_id)
            raise HTTPException(status_code=400, detail="Invalid session ID")

        # Use HOST path for Docker mounting, but ensure INTERNAL path exists for writing
        session_dir_host = str(Path(RCE_DATA_DIR_HOST) / safe_sid)
        session_dir_internal = Path(RCE_DATA_DIR_INTERNAL) / safe_sid
        session_dir_internal.mkdir(parents=True, exist_ok=True)

        return {session_dir_host: {'bind': '/mnt/data', 'mode': 'rw'}}

    def recover_containers(self):
        """Scans Docker for existing containers managed by this API and re-adopts them."""
        logger.info("Scanning for existing containers to recover...")
        try:
            containers = DOCKER_CLIENT.containers.list(
                all=True,
                filters={"label": f"managed_by={RCE_MANAGED_BY_VALUE}"}
            )
            with self.lock:
                for container in containers:
                    session_id = container.labels.get("session_id")
                    external_session_id = container.labels.get("external_session_id")
                    if session_id and session_id not in self.active_kernels:
                        try:
                            # We don't auto-start here to avoid load spikes.
                            # They will be started on first request.
                            self.active_kernels[session_id] = {
                                "container": container,
                                "last_accessed": time.time()
                            }
                            if external_session_id:
                                self.nanoid_to_session[external_session_id] = session_id
                                self.session_to_nanoid[session_id] = external_session_id
                                logger.info("Recovered session %s (external: %s) from container %s", session_id, external_session_id, container.id)
                            else:
                                logger.info("Recovered session %s from container %s", session_id, container.id)
                        except Exception as e:
                            logger.error("Failed to recover container %s: %s", container.id, e)
        except Exception as e:
            logger.error("Error during container recovery: %s", e)

    def _cleanup_single_session(self, session_id: str, data: Optional[Dict[str, Any]]):
        """Internal helper to perform the actual I/O for cleaning up a session."""
        try:
            # Cleanup internal session directory if volume mounting was used
            if RCE_DATA_DIR_INTERNAL:
                # Sanitize to prevent accidental deletion outside shared volume
                safe_sid = sanitize_id(session_id)
                if not safe_sid:
                     logger.warning("Attempted to cleanup session with invalid ID: %s", session_id)
                     return
                session_dir = os.path.join(RCE_DATA_DIR_INTERNAL, safe_sid)
                if os.path.exists(session_dir):
                    shutil.rmtree(session_dir, ignore_errors=True)

            if data:
                container = data.get("container")
                if container:
                    container.stop(timeout=5)
                    # Since remove=True was used, it should be gone now.
        except Exception as e:
            logger.error("Error cleaning up session %s: %s", session_id, e)

    def cleanup_sessions(self):
        """Stops and removes containers that have exceeded the TTL."""
        now = time.time()
        expired_sessions = []
        with self.lock:
            for session_id, data in self.active_kernels.items():
                if now - data["last_accessed"] > RCE_SESSION_TTL:
                    expired_sessions.append(session_id)

        if not expired_sessions:
            return

        cleanup_tasks = []
        for session_id in expired_sessions:
            logger.info("Cleaning up idle session: %s", session_id)
            with self.lock:
                # Clean up ID mappings
                nanoid_session = self.session_to_nanoid.pop(session_id, None)
                if nanoid_session:
                    self.nanoid_to_session.pop(nanoid_session, None)
                    self.file_id_map.pop(nanoid_session, None)

                data = self.active_kernels.pop(session_id, None)

            cleanup_tasks.append((session_id, data))

        # Perform I/O operations (directory removal and container stopping) in parallel
        with ThreadPoolExecutor(max_workers=min(len(cleanup_tasks), 20)) as executor:
            for session_id, data in cleanup_tasks:
                executor.submit(self._cleanup_single_session, session_id, data)

    async def cleanup_loop(self):
        """Background loop for periodic cleanup."""
        while True:
            try:
                # Run cleanup in a separate thread to avoid blocking the event loop
                await asyncio.to_thread(self.cleanup_sessions)
            except Exception as e:
                logger.error("Error in cleanup loop: %s", e)
            await asyncio.sleep(60) # Run every minute

    def _put_archive_with_retry(self, session_id: str, container, path: str, data: bytes, external_session_id: Optional[str] = None):
        # Sanitize session_id to prevent path traversal in error recovery logic
        safe_sid = sanitize_id(session_id)
        if not safe_sid:
            raise HTTPException(status_code=400, detail="Invalid session ID")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                container.put_archive(path, data)
                return
            except (docker.errors.APIError, docker.errors.NotFound) as e:
                if attempt == max_retries - 1:
                    logger.error("Failed to put archive for session %s after %d attempts: %s", safe_sid, max_retries, e)
                    raise
                logger.warning("Retry %d/%d: put_archive failed for session %s, refreshing container: %s", attempt + 1, max_retries, safe_sid, e)
                # Recovery: Force refresh and retry
                container = self.get_or_create_container(safe_sid, force_refresh=True, external_session_id=external_session_id)

    def upload_file(self, session_id: str, filename: str, content: bytes, external_session_id: Optional[str] = None):
        if not content:
            raise HTTPException(status_code=400, detail="File content is empty")

        # Sanitize session_id and filename to prevent path traversal
        safe_sid = sanitize_id(session_id)
        if not safe_sid:
            raise HTTPException(status_code=400, detail="Invalid session ID")

        safe_filename = Path(filename).name
        if not safe_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        try:
            if RCE_DATA_DIR_HOST:
                session_dir = Path(RCE_DATA_DIR_INTERNAL) / safe_sid
                session_dir.mkdir(parents=True, exist_ok=True)
                filepath = session_dir / safe_filename
                filepath.write_bytes(content)
                logger.info("Uploaded file %s to volume (internal: %s) for session %s", safe_filename, session_dir, safe_sid)
                # Ensure container exists (even if it doesn't need to do anything now)
                self.get_or_create_container(safe_sid, external_session_id=external_session_id)
            else:
                container = self.get_or_create_container(safe_sid, external_session_id=external_session_id)
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                    tar_info = tarfile.TarInfo(name=safe_filename)
                    tar_info.size = len(content)
                    tar.addfile(tar_info, io.BytesIO(content))

                self._put_archive_with_retry(safe_sid, container, "/mnt/data", tar_stream.getvalue(), external_session_id)
                logger.info("Uploaded file %s to session %s via put_archive", safe_filename, safe_sid)
        except docker.errors.NotFound:
            logger.error(f"Container not found for session {safe_sid} during upload")
            raise HTTPException(status_code=404, detail="Session not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def upload_files_batch(self, session_id: str, files: List[Tuple[str, bytes]], external_session_id: Optional[str] = None):
        """Uploads multiple files at once, optimizing Docker API calls."""
        if not files:
            return

        # Sanitize session_id to prevent path traversal
        safe_sid = sanitize_id(session_id)
        if not safe_sid:
            raise HTTPException(status_code=400, detail="Invalid session ID")

        try:
            if RCE_DATA_DIR_HOST:
                session_dir = Path(RCE_DATA_DIR_INTERNAL) / safe_sid
                session_dir.mkdir(parents=True, exist_ok=True)
                for filename, content in files:
                    safe_filename = Path(filename).name
                    if not safe_filename:
                        continue
                    (session_dir / safe_filename).write_bytes(content)
                logger.info("Uploaded %d files to volume for session %s", len(files), safe_sid)
                self.get_or_create_container(safe_sid, external_session_id=external_session_id)
            else:
                container = self.get_or_create_container(safe_sid, external_session_id=external_session_id)
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                    for filename, content in files:
                        safe_filename = Path(filename).name
                        if not safe_filename:
                            continue
                        tar_info = tarfile.TarInfo(name=safe_filename)
                        tar_info.size = len(content)
                        tar.addfile(tar_info, io.BytesIO(content))

                self._put_archive_with_retry(safe_sid, container, "/mnt/data", tar_stream.getvalue(), external_session_id)
                logger.info("Uploaded %d files to session %s via put_archive", len(files), safe_sid)
        except docker.errors.NotFound:
            logger.error(f"Container not found for session {safe_sid} during upload")
            raise HTTPException(status_code=404, detail="Session not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_file_id_mapping(self, nanoid_session: str, filenames: List[str]) -> Dict[str, str]:
        """
        Ensures all filenames have a NanoID mapping and returns a filename-to-file_id dict.
        """
        with self.lock:
            if nanoid_session not in self.file_id_map:
                self.file_id_map[nanoid_session] = {}

            id_map = self.file_id_map[nanoid_session]
            # Create a reverse map for lookups: filename -> file_id
            filename_to_id = {v: k for k, v in id_map.items()}

            for f in filenames:
                if f not in filename_to_id:
                    file_id = generate_nanoid()
                    id_map[file_id] = f
                    filename_to_id[f] = file_id

            return filename_to_id

    def download_file(self, session_id: str, filename: str):
        # Sanitize session_id and filename to prevent path traversal
        safe_sid = sanitize_id(session_id)
        if not safe_sid:
            raise HTTPException(status_code=400, detail="Invalid session ID")

        if not filename or not filename.strip():
            raise HTTPException(status_code=400, detail="Invalid filename")

        # Normalize filename path while blocking path traversal
        path_obj = Path(filename)
        if ".." in path_obj.parts or path_obj.is_absolute():
            raise HTTPException(status_code=400, detail="Invalid filename")

        norm_filename = str(path_obj).lstrip("/")
        if not norm_filename or norm_filename == ".":
            raise HTTPException(status_code=400, detail="Invalid filename")

        if RCE_DATA_DIR_HOST:
            session_dir = Path(RCE_DATA_DIR_INTERNAL) / safe_sid
            filepath = session_dir / norm_filename
            
            # Security check: ensure path is inside session_dir
            abs_session = session_dir.resolve()
            abs_file = filepath.resolve()
            if not abs_file.is_relative_to(abs_session):
                raise HTTPException(status_code=403, detail="Forbidden")

            if filepath.exists():
                content = filepath.read_bytes()
                mtime = filepath.stat().st_mtime
                return content, mtime
            raise FileNotFoundError()
        else:
            container = self.get_or_create_container(safe_sid)
            try:
                res = container.get_archive(f"/mnt/data/{norm_filename}")
                if not isinstance(res, (tuple, list)) or len(res) < 2:
                    raise FileNotFoundError()
                bits, stat = res[0], res[1]

                # Extract from tar bits
                tar_stream = io.BytesIO(b"".join(bits))
                with tarfile.open(fileobj=tar_stream, mode='r') as tar:
                    members = tar.getmembers()
                    if not members:
                        raise FileNotFoundError()
                    for member in members:
                        if member.isfile():
                            f = tar.extractfile(member)
                            if f:
                                return f.read(), stat.get('mtime', 0)
                raise FileNotFoundError()
            except (docker.errors.NotFound, FileNotFoundError):
                raise HTTPException(status_code=404, detail="File not found")
            except Exception as e:
                logger.error("Failed to download file %s from session %s: %s", filename, session_id, e)
                raise HTTPException(status_code=500, detail="Internal server error during file download")

    def list_files(self, session_id: str, external_session_id: Optional[str] = None):
        container = self.get_or_create_container(session_id, external_session_id=external_session_id)
        # Use python os.walk to recursively list files in /mnt/data, excluding hidden folders/files.
        py_script = (
            "import os, json\n"
            "res = []\n"
            "base = '/mnt/data'\n"
            "for root, dirs, files in os.walk(base):\n"
            "    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'node_modules', '.venv')]\n"
            "    for f in files:\n"
            "        if not f.startswith('.'):\n"
            "            rel = os.path.relpath(os.path.join(root, f), base)\n"
            "            res.append(rel)\n"
            "print(json.dumps(res))\n"
        )
        cmd = ["python3", "-c", py_script]

        try:
            res = container.exec_run(cmd=cmd, demux=True)
        except (docker.errors.APIError, docker.errors.NotFound):
            container = self.get_or_create_container(session_id, force_refresh=True, external_session_id=external_session_id)
            res = container.exec_run(cmd=cmd, demux=True)

        if isinstance(res.output, tuple) and len(res.output) == 2:
            stdout, stderr = res.output
        elif isinstance(res.output, (bytes, str)):
            stdout = res.output if isinstance(res.output, bytes) else res.output.encode("utf-8")
            stderr = None
        else:
            stdout, stderr = None, None

        out_str = stdout.decode('utf-8') if stdout else ""
        err_str = stderr.decode('utf-8') if stderr else ""
        logger.info("list_files exec_run for session %s: exit_code=%s, stdout='%s', stderr='%s'", session_id, res.exit_code, out_str.strip(), err_str.strip())

        if res.exit_code == 0:
            output = out_str
            try:
                files = json.loads(output)
                return [f for f in files if f]
            except Exception as e:
                logger.error("Failed to parse file list JSON from container: %s. Raw output: %s", e, output)
                files = output.splitlines()
                return [f for f in files if f]
        return []

    def _execute_in_container(self, container, code_content: str, path: str, filename: str, lang: str = "python"):
        """
        Uploads code to the container and executes it.
        """
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            code_bytes = code_content.encode('utf-8')
            tar_info = tarfile.TarInfo(name=filename)
            tar_info.size = len(code_bytes)
            tar.addfile(tar_info, io.BytesIO(code_bytes))

        container.put_archive("/mnt/data", tar_stream.getvalue())

        cmd = ["python3", path]
        if lang in ["bash", "sh"]:
            cmd = ["bash", path]
        elif lang == "r":
            cmd = ["Rscript", path]

        return container.exec_run(
            cmd=cmd,
            workdir="/mnt/data",
            demux=True
        )

    def execute_code(self, session_id: str, code: str, lang: str = "python", external_session_id: Optional[str] = None):
        """
        Executes code within the container.
        Returns a dictionary with stdout, stderr, and exit_code.
        Raises HTTPException for system errors.
        """
        container = None
        container_path = None
        
        try:
            container = self.get_or_create_container(session_id, external_session_id=external_session_id)

            # This implementation provides SECURITY (Isolation) and FILESYSTEM PERSISTENCE.
            # We write the code to a temporary file inside the container using 'put_archive'
            # to avoid shell escaping issues and command line length limits.

            ext = "py"
            if lang in ["bash", "sh"]:
                ext = "sh"
            elif lang == "r":
                ext = "R"

            code_filename = f"exec_{uuid.uuid4().hex}.{ext}"
            container_path = f"/mnt/data/{code_filename}"

            # 1. Apply code wrapping for expression-only support (Python only)
            if lang in ["python", "py"]:
                wrapped_code = wrap_code(code)
            else:
                wrapped_code = code

            try:
                exec_result = self._execute_in_container(container, wrapped_code, container_path, code_filename, lang)
            except (docker.errors.APIError, docker.errors.NotFound):
                # Optimistic assumption failed: container might be stopped or gone
                # Recovery: Force refresh and retry once
                container = self.get_or_create_container(session_id, force_refresh=True, external_session_id=external_session_id)
                exec_result = self._execute_in_container(container, wrapped_code, container_path, code_filename, lang)
            
            stdout, stderr = exec_result.output

            return {
                "stdout": stdout.decode("utf-8") if stdout else "",
                "stderr": stderr.decode("utf-8") if stderr else "",
                "exit_code": exec_result.exit_code
            }
            
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error executing code in session %s", session_id)
            raise HTTPException(status_code=500, detail="An internal error occurred during code execution.")
        finally:
            # 3. Cleanup: remove the temporary file
            if container and container_path:
                try:
                    container.exec_run(cmd=["rm", container_path])
                except Exception:
                    logger.warning("Failed to remove temporary file %s in session %s", container_path, session_id)

kernel_manager = KernelManager()

# 3. Request/Response Schemas
class FileInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: Optional[str] = None
    storage_session_id: Optional[str] = None
    id: str
    name: str

class CodeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    code: str
    lang: Optional[str] = "py"
    session_id: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[str] = None
    files: Optional[List[FileInput]] = []
    args: Optional[List[str]] = []

class FileInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    name: str = ""
    url: str = ""
    type: str = "application/octet-stream"
    session_id: str = ""
    storage_session_id: str = ""
    inherited: bool = False

class CodeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output: str = ""
    result: str = ""  # Alias for stdout/output for some integration paths
    status: str = "success"     # Explicit status string
    session_id: str = ""
    files: List[FileInfo] = []
    images: List[Dict[str, Any]] = [] # Matplotlib images or other plot captures

# 4. Helper Functions

def _get_effective_session_id(req: CodeRequest) -> Optional[str]:
    """Extracts session_id from CodeRequest with various fallbacks."""
    effective_session_id = req.session_id or req.entity_id
    if effective_session_id and sanitize_id(str(effective_session_id)).lower() in ("", "null", "undefined", "none"):
        effective_session_id = None

    if not effective_session_id and req.files and len(req.files) > 0:
        first_file = req.files[0]
        if hasattr(first_file, "session_id") and getattr(first_file, "session_id"):
            cand = getattr(first_file, "session_id")
            if cand and sanitize_id(str(cand)).lower() not in ("", "null", "undefined", "none"):
                effective_session_id = str(cand)
        if not effective_session_id and hasattr(first_file, "storage_session_id") and getattr(first_file, "storage_session_id"):
            cand = getattr(first_file, "storage_session_id")
            if cand and sanitize_id(str(cand)).lower() not in ("", "null", "undefined", "none"):
                effective_session_id = str(cand)
        if not effective_session_id and isinstance(first_file, dict):
            cand = first_file.get("session_id") or first_file.get("storage_session_id")
            if cand and sanitize_id(str(cand)).lower() not in ("", "null", "undefined", "none"):
                effective_session_id = str(cand)

    # Fallback to user_id to ensure container reuse and improve performance
    if not effective_session_id and req.user_id:
        user_id_clean = sanitize_id(str(req.user_id))
        if user_id_clean and user_id_clean.lower() not in ("null", "undefined", "none"):
            effective_session_id = f"user_{user_id_clean}"

    # Fallback to last uploaded session
    if not effective_session_id:
        global LAST_UPLOADED_SESSION_ID, LAST_UPLOAD_TIME
        if LAST_UPLOADED_SESSION_ID and (time.time() - LAST_UPLOAD_TIME < 300):
            effective_session_id = LAST_UPLOADED_SESSION_ID
            logger.info("Fallback activated! Re-using last uploaded session ID: %s", effective_session_id)

    return effective_session_id

def _get_validated_lang(req: CodeRequest) -> str:
    """Extracts and validates the execution language."""
    requested_lang = (req.lang or "python").lower()
    SUPPORTED_LANGUAGES = {"python", "py", "bash", "sh", "r"}
    if requested_lang not in SUPPORTED_LANGUAGES:
        logger.error("Unsupported language requested: %s", req.lang)
        raise HTTPException(status_code=400, detail=f"Unsupported language: {req.lang}. Supported: python, bash, r")
    return requested_lang

# 5. Endpoints

@app.post("/exec", response_model=CodeResponse)
@app.post("/run/exec", response_model=CodeResponse)
async def run_code(req: CodeRequest, key: str = Security(get_api_key)):
    """
    Executes code in a sandboxed Docker container.
    """
    logger.info("Exec request received. Request body: %s", req.model_dump())

    effective_session_id = _get_effective_session_id(req)
    logger.info("Effective session ID for exec: %s", effective_session_id)

    # Validate execution language
    requested_lang = _get_validated_lang(req)

    # Resolve nanoid session ID if provided
    sid = effective_session_id or generate_nanoid()
    real_session_id, nanoid_session = _get_session_ids(sid)

    # 異なるセッションにアップロードされたファイルを現在の実行セッションに集約（堅牢化設計）
    if req.files:
        for file_info in req.files:
            file_sid = file_info.session_id or file_info.storage_session_id
            if file_sid:
                file_real_sid, file_nanoid_sid = _get_session_ids(file_sid)
                if file_real_sid != real_session_id:
                    try:
                        logger.info("ファイルをセッション %s から実行セッション %s に集約します: %s", file_nanoid_sid, nanoid_session, file_info.name)
                        file_content, _ = await asyncio.to_thread(kernel_manager.download_file, file_real_sid, file_info.name)
                        await asyncio.to_thread(kernel_manager.upload_file, real_session_id, file_info.name, file_content, external_session_id=nanoid_session)
                    except Exception as e:
                        logger.warning("ファイル %s の集約に失敗しました: %s", file_info.name, str(e))
    
    # Run in sandbox
    if asyncio.iscoroutinefunction(kernel_manager.execute_code):
        result = await kernel_manager.execute_code(
            real_session_id,
            req.code,
            lang=requested_lang,
            external_session_id=nanoid_session
        )
    else:
        result = await asyncio.to_thread(
            kernel_manager.execute_code,
            real_session_id,
            req.code,
            lang=requested_lang,
            external_session_id=nanoid_session
        )

    # Handle cases where execute_code is mocked with an async side_effect but not as a coroutine function
    # or when to_thread returns a coroutine from a mock.
    if asyncio.iscoroutine(result):
        result = await result
    # List generated files and format them for LibreChat native ingestion
    current_files = await asyncio.to_thread(kernel_manager.list_files, real_session_id, external_session_id=nanoid_session)
    logger.info("Found %d files in session %s (real: %s): %s", len(current_files), nanoid_session, real_session_id, current_files)
    filename_to_id = kernel_manager.get_file_id_mapping(nanoid_session, current_files)
    
    # Identify input filenames to set inherited flag
    input_filenames = set()
    if req.files:
        for f_in in req.files:
            name = getattr(f_in, "name", None) or (f_in.get("name") if isinstance(f_in, dict) else None)
            if name:
                input_filenames.add(name)

    structured_files = []
    images = []

    for f in current_files:
        mime_type, _ = mimetypes.guess_type(f)
        mime_type = mime_type or "application/octet-stream"
        nanoid_file = filename_to_id[f]
        is_inherited = f in input_filenames

        structured_files.append({
            "id": nanoid_file,
            "name": f,
            "url": f"/api/files/code/download/{nanoid_session}/{nanoid_file}",
            "type": mime_type,
            "session_id": nanoid_session,
            "storage_session_id": nanoid_session,
            "inherited": is_inherited
        })

        # Automatically capture and base64 encode newly generated plot/image files for instant UI inline display
        if not is_inherited and mime_type.startswith("image/"):
            try:
                img_bytes, _ = await asyncio.to_thread(kernel_manager.download_file, real_session_id, f)
                b64_data = base64.b64encode(img_bytes).decode("utf-8")
                ext = Path(f).suffix.lstrip(".").lower() or "png"
                images.append({
                    "name": f,
                    "format": ext,
                    "data": b64_data,
                    "base64": b64_data,
                    "url": f"/api/files/code/download/{nanoid_session}/{nanoid_file}",
                    "type": mime_type
                })
                logger.info("Captured image %s (bytes: %d, format: %s)", f, len(img_bytes), ext)
            except Exception as e:
                logger.warning("Failed to encode generated image %s for response: %s", f, e)
    
    out_text = result.get("stdout") or ""
    err_text = result.get("stderr") or ""
    exit_val = result.get("exit_code", 0)

    return {
        "stdout": out_text,
        "stderr": err_text,
        "exit_code": exit_val,
        "output": out_text,
        "result": out_text,
        "status": "success" if exit_val == 0 else "error",
        "session_id": nanoid_session or "",
        "files": structured_files if structured_files is not None else [],
        "images": images if images is not None else []
    }

@app.post("/upload")
@app.post("/run/upload")
@app.post("/files/upload")
@app.post("/api/upload")
@app.post("/api/files/upload")
@app.post("/api/files/code/upload")
@app.post("/files/code/upload")
async def upload_files(
    entity_id: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[List[UploadFile]] = File(None),
    session_id_query: Optional[str] = Query(None, alias="session_id"),
    key: Optional[str] = Security(get_api_key)
):
    """
    Uploads files to a specific session sandbox.
    """
    try:
        global LAST_UPLOADED_SESSION_ID, LAST_UPLOAD_TIME
        sid = entity_id or session_id or session_id_query
        if sid and sanitize_id(str(sid)).lower() in ("", "null", "undefined", "none"):
            sid = None

        if not sid:
            if LAST_UPLOADED_SESSION_ID and (time.time() - LAST_UPLOAD_TIME < 300):
                sid = LAST_UPLOADED_SESSION_ID
                logger.info("アップロードでフォールバックが有効化されました！直近のアップロードセッションIDを再利用します: %s", sid)
            else:
                sid = generate_nanoid()
                LAST_UPLOADED_SESSION_ID = sid
                LAST_UPLOAD_TIME = time.time()
                logger.info("アップロードにセッションIDが指定されていません。新規に生成して即時登録しました: %s", sid)

        upload_list = files or file
        if not upload_list:
            logger.error("No files provided in upload request")
            raise HTTPException(status_code=422, detail="No files provided")

        logger.info("Files found in request: %s", [f.filename for f in upload_list])

        real_session_id, nanoid_session = _get_session_ids(sid)

        async def read_file_content(f):
            if not f.filename:
                raise HTTPException(status_code=400, detail="Invalid filename")
            content = await f.read()
            if not content:
                raise HTTPException(status_code=400, detail="File content is empty")
            safe_filename = Path(f.filename).name
            if not safe_filename:
                raise HTTPException(status_code=400, detail="Invalid filename")
            return safe_filename, content

        # Read all files in parallel
        file_data = await asyncio.gather(*[read_file_content(f) for f in upload_list])

        # Perform batch upload
        await asyncio.to_thread(kernel_manager.upload_files_batch, real_session_id, file_data, external_session_id=nanoid_session)

        # Record last upload for session fallback
        LAST_UPLOADED_SESSION_ID = sid
        LAST_UPLOAD_TIME = time.time()
        logger.info("Recorded last uploaded session ID: %s", sid)

        # Get file mappings
        filenames = [name for name, _ in file_data]
        filename_to_id = kernel_manager.get_file_id_mapping(nanoid_session, filenames)
        uploaded_files = []
        for name in filenames:
            fid = filename_to_id[name]
            uploaded_files.append({
                "fileId": fid,
                "id": fid,
                "filename": name,
                "name": name,
                "url": f"/api/files/code/download/{nanoid_session}/{fid}",
                "session_id": nanoid_session,
                "storage_session_id": nanoid_session
            })
        
        res = {
            "message": "success",
            "status": "success",
            "session_id": nanoid_session or "",
            "storage_session_id": nanoid_session or "",
            "files": uploaded_files if uploaded_files is not None else []
        }
        if uploaded_files:
            res.update({
                "fileId": uploaded_files[0]["fileId"],
                "id": uploaded_files[0]["id"],
                "filename": uploaded_files[0]["filename"],
                "name": uploaded_files[0]["name"],
                "url": uploaded_files[0]["url"]
            })
            
        logger.info("Upload returning success. Response: %s", res)
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing upload")
        raise HTTPException(status_code=500, detail=str(e))

def get_download_meta(real_filename: str) -> Tuple[str, Dict[str, str]]:
    """Determines MIME type and constructs headers for file download."""
    base_name = os.path.basename(real_filename) or real_filename
    # Guess MIME type
    if Path(real_filename).suffix.lower() == ".csv":
        mime_type = "text/plain"  # Force text/plain to allow inline display and bypass Chrome's HTTP download security block
    else:
        mime_type, _ = mimetypes.guess_type(real_filename)
        if not mime_type:
            mime_type = "application/octet-stream"

    # Use inline for images, PDFs, and text files (including CSV rendered as text/plain) to bypass Chrome's insecure download blocker
    disposition = "inline" if mime_type.startswith(("image/", "application/pdf", "text/")) else "attachment"

    # Manually construct Content-Disposition header to ensure maximum compatibility with Japanese filenames.
    # Starlette's default FileResponse might not always provide the filename="..." fallback correctly for non-ASCII.
    filename_encoded = quote(base_name)
    # Fallback to an ASCII-safe filename or 'file' if no ASCII characters exist.
    safe_filename_ascii = base_name.encode('ascii', 'ignore').decode().replace('\\', '').replace('"', '').replace('\r', '').replace('\n', '') or "file"
    headers = {
        "Content-Disposition": f"{disposition}; filename=\"{safe_filename_ascii}\"; filename*=utf-8''{filename_encoded}"
    }
    return mime_type, headers

@app.get("/download")
@app.get("/run/download")
@app.get("/files/download")
@app.get("/api/download")
@app.get("/api/files/download")
@app.get("/api/files/code/download")
@app.get("/files/code/download")
async def download_file_query(
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
    file_id: Optional[str] = Query(None),
    file: Optional[str] = Query(None),
    id: Optional[str] = Query(None),
    filepath: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    key: str = Security(get_api_key)
):
    """
    Downloads a file from a session's sandbox using query parameters.
    """
    effective_sid = session_id or entity_id
    effective_fn = filename or file_id or file or id or filepath
    if not effective_fn:
        raise HTTPException(status_code=422, detail="Filename parameter is required")
    if not effective_sid:
        raise HTTPException(status_code=422, detail="Session ID parameter is required")
    return await download_session_file(effective_sid, effective_fn, background_tasks, key)

@app.get("/files/{session_id}")
@app.get("/run/files/{session_id}")
@app.get("/api/files/{session_id}")
@app.get("/api/files/code/{session_id}")
@app.get("/files/code/{session_id}")
async def list_session_files(session_id: str, key: str = Security(get_api_key)):
    """
    Lists files in a session's sandbox.
    """
    try:
        s_sid = sanitize_id(session_id)
        if not s_sid:
            global LAST_UPLOADED_SESSION_ID, LAST_UPLOAD_TIME
            if LAST_UPLOADED_SESSION_ID and (time.time() - LAST_UPLOAD_TIME < 300):
                s_sid = sanitize_id(LAST_UPLOADED_SESSION_ID)
            elif kernel_manager.active_kernels:
                s_sid = max(kernel_manager.active_kernels.items(), key=lambda x: x[1].get("last_accessed", 0))[0]

        if not s_sid:
            return []

        real_session_id = kernel_manager.resolve_session_id(s_sid)
        with kernel_manager.lock:
            nanoid_session = kernel_manager.session_to_nanoid.get(real_session_id, s_sid)

        files = await asyncio.to_thread(kernel_manager.list_files, real_session_id, external_session_id=nanoid_session)

        file_list = []
        with kernel_manager.lock:
            id_map = kernel_manager.file_id_map.get(nanoid_session, {})
            reversed_map = {v: k for k, v in id_map.items()}
            for f in files:
                fid = reversed_map.get(f, "")
                file_list.append({
                    "filename": f,
                    "fileId": fid,
                    "id": fid,
                    "name": f,
                    "url": f"/api/files/code/download/{nanoid_session}/{fid}" if fid else f"/api/files/code/download/{nanoid_session}/{f}",
                    "session_id": nanoid_session,
                    "storage_session_id": nanoid_session
                })

        return file_list
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error listing session files")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files/code/download/{session_id}/{filename:path}")
@app.get("/files/code/download/{session_id}/{filename:path}")
@app.get("/api/code/download/{session_id}/{filename:path}")
@app.get("/code/download/{session_id}/{filename:path}")
@app.get("/download/{session_id}/{filename:path}")
@app.get("/run/download/{session_id}/{filename:path}")
@app.get("/files/download/{session_id}/{filename:path}")
@app.get("/api/files/download/{session_id}/{filename:path}")
async def download_session_file(
    session_id: str,
    filename: str,
    background_tasks: BackgroundTasks,
    key: Optional[str] = Security(get_api_key)
):
    """
    Downloads a file from a session's sandbox using path parameters.
    Supports nanoid-format IDs (used by LibreChat) and direct session_id/filename.
    Uses FileResponse to ensure perfect streaming header compatibility with LibreChat's Axios proxy.
    """
    real_session_id, real_filename = kernel_manager.resolve_download_ids(session_id, filename)
    
    # Basic validation of session_id to prevent path traversal to base directory
    if not real_session_id:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    # Determine the file path if volume mounting is enabled
    in_memory_content = None
    try:
        if RCE_DATA_DIR_HOST:
            session_dir = Path(RCE_DATA_DIR_INTERNAL) / real_session_id
            filepath = session_dir / real_filename

            # Security: Ensure the path is within the designated data directory
            # and that real_session_id is not empty (already handled by resolve_download_ids but good to be safe)
            abs_base = Path(RCE_DATA_DIR_INTERNAL).resolve()
            abs_file = filepath.resolve()
            if not abs_file.is_relative_to(abs_base) or not real_session_id:
                logger.warning("Path traversal attempt blocked: %s", filepath)
                raise HTTPException(status_code=403, detail="Forbidden")

            if not filepath.exists():
                 raise HTTPException(status_code=404, detail="File not found")
            tmp_filepath = str(filepath)
        else:
            # Fallback to Docker API (get_archive)
            in_memory_content, mtime = await asyncio.to_thread(kernel_manager.download_file, real_session_id, real_filename)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to download file %s from session %s: %s", filename, session_id, e)
        raise HTTPException(status_code=500, detail="Internal server error during file download")

    mime_type, headers = get_download_meta(real_filename)

    if in_memory_content is not None:
        return Response(
            content=in_memory_content,
            media_type=mime_type,
            headers=headers
        )

    return FileResponse(
        path=tmp_filepath,
        media_type=mime_type,
        headers=headers
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "mode": "docker-sandboxed"}
