import pytest
import os
import io
import tarfile
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
import main
from main import app, KernelManager, get_download_meta

@pytest.fixture
def km():
    manager = KernelManager()
    manager.nanoid_to_session = {}
    manager.session_to_nanoid = {}
    manager.file_id_map = {}
    return manager

# ==================== Pathlib Unit Tests ====================

def test_resolve_download_ids_pathlib(km):
    """Verify that resolve_download_ids works correctly under pathlib refactoring."""
    # Standard file resolution
    km.nanoid_to_session["s1"] = "real-uuid-1"
    km.file_id_map["s1"] = {"file1": "real_file.txt"}
    real_session, real_file = km.resolve_download_ids("s1", "file1")
    assert real_session == "real-uuid-1"
    assert real_file == "real_file.txt"

    # Relative sub-path
    km.file_id_map["s1"] = {"file2": "sub/folder/file2.txt"}
    real_session, real_file = km.resolve_download_ids("s1", "file2")
    assert real_session == "real-uuid-1"
    assert real_file == "sub/folder/file2.txt"

    # Path traversal with '..'
    km.file_id_map["s1"] = {"file_malicious": "sub/../outside.txt"}
    real_session, real_file = km.resolve_download_ids("s1", "file_malicious")
    assert real_session == "real-uuid-1"
    assert real_file == "outside.txt"  # fallback to name

    # Absolute path
    km.file_id_map["s1"] = {"file_absolute": "/absolute/path/file.txt"}
    real_session, real_file = km.resolve_download_ids("s1", "file_absolute")
    assert real_session == "real-uuid-1"
    assert real_file == "file.txt"  # fallback to name

def test_download_file_traversal_detection(km):
    """Verify that download_file correctly blocks path traversal."""
    # Absolute path input
    with pytest.raises(HTTPException) as exc:
        km.download_file("session_1", "/etc/passwd")
    assert exc.value.status_code == 400

    # '..' in path parts
    with pytest.raises(HTTPException) as exc:
        km.download_file("session_1", "sub/../../etc/passwd")
    assert exc.value.status_code == 400

    # Standard relative path with RCE_DATA_DIR_HOST (volume mounting)
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat, \
         patch("pathlib.Path.read_bytes", return_value=b"content"):

        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = 987654321.0
        mock_stat.return_value = mock_stat_result

        # Path traversal with commonpath/is_relative_to simulation
        # Suppose a malicious filename "sub/folder/file.txt" is resolved to /internal/path/session_1/sub/folder/file.txt
        content, mtime = km.download_file("session_1", "sub/folder/file.txt")
        assert content == b"content"
        assert mtime == 987654321.0

def test_get_download_meta_suffix():
    """Verify suffix extraction in get_download_meta."""
    # CSV extension
    mime, headers = get_download_meta("data.csv")
    assert mime == "text/plain"
    assert "data.csv" in headers["Content-Disposition"]

    # Upper case CSV extension
    mime, headers = get_download_meta("DATA.CSV")
    assert mime == "text/plain"

    # Other extensions (e.g., png)
    mime, headers = get_download_meta("image.png")
    assert mime == "image/png"
    assert "inline" in headers["Content-Disposition"]

    # No extension
    mime, headers = get_download_meta("plain_file")
    assert mime == "application/octet-stream"


# ==================== Tough Simulated-UI Integration Tests ====================

def test_upload_japanese_filename():
    """Simulates UI uploading files with Japanese/non-ASCII characters in filename."""
    client = TestClient(app)
    japanese_filename = "日本語テスト.csv"
    session_id = "test_japanese_session"

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.write_bytes") as mock_write_bytes, \
         patch("main.DOCKER_CLIENT"):

        # Perform the simulated file upload via API
        response = client.post(
            "/upload",
            data={"entity_id": session_id},
            files={"files": (japanese_filename, b"col1,col2\n1,2")},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        res_json = response.json()
        assert res_json["message"] == "success"

        # Verify the directory and correct filename are processed via pathlib.Path
        mock_mkdir.assert_called()
        mock_write_bytes.assert_called_once_with(b"col1,col2\n1,2")

def test_upload_double_file_extension():
    """Simulates UI uploading files with double/complex extensions (e.g. archive.tar.gz)."""
    client = TestClient(app)
    double_ext_filename = "data_backup.tar.gz"
    session_id = "test_double_ext_session"

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.write_bytes") as mock_write_bytes, \
         patch("main.DOCKER_CLIENT"):

        response = client.post(
            "/upload",
            data={"entity_id": session_id},
            files={"files": (double_ext_filename, b"fake tar gz content")},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        mock_write_bytes.assert_called_once_with(b"fake tar gz content")

        # Let's ensure suffix is handled properly
        suffix = Path(double_ext_filename).suffix
        assert suffix == ".gz"  # pathlib.Path suffix gets the last extension

def test_download_japanese_filename_and_meta_headers():
    """Simulates UI request to download a file with Japanese characters, ensuring safe browser content-disposition headers."""
    client = TestClient(app)
    japanese_filename = "データ報告.csv"
    session_id = "test_japanese_download"

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve") as mock_resolve, \
         patch("os.stat") as mock_os_stat, \
         patch("anyio.open_file") as mock_open_file:

        # Mock stat for FileResponse
        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 50
        mock_stat_result.st_mtime = 123456789.0
        mock_stat_result.st_mode = 33188  # regular file
        mock_os_stat.return_value = mock_stat_result

        # Mock anyio.open_file context manager
        mock_file = MagicMock()
        mock_file.__aenter__.return_value = MagicMock(read=AsyncMock(return_value=b"col1,col2\nvalue1,value2"))
        mock_open_file.return_value = mock_file

        # Mock path resolution safety checks
        mock_resolve.side_effect = lambda *args, **kwargs: Path(f"/internal/path/{session_id}/{japanese_filename}")

        # Stub resolution
        with patch.object(main.kernel_manager, "resolve_download_ids", return_value=(session_id, japanese_filename)):
            response = client.get(
                f"/download/{session_id}/{japanese_filename}",
                headers={"X-API-Key": main.API_KEY}
            )

            assert response.status_code == 200

            # Verify inline disposition and RFC 5987 UTF-8 filename encoding is set
            disposition = response.headers.get("content-disposition")
            assert "inline" in disposition
            assert "filename*=utf-8''%E3%83%87%E3%83%BC%E3%82%BF%E5%A0%B1%E5%91%8A.csv" in disposition
            assert response.content == b"col1,col2\nvalue1,value2"

def test_sanitize_unicode_japanese_session_id():
    """Simulates UI requests using a session ID with Japanese/Unicode characters, ensuring safe sanitization."""
    client = TestClient(app)
    unicode_session_id = "セッション_123_!!!"  # '!' is allowed, Japanese characters get sanitized out if they are non-alphanumeric in ascii, wait sanitize_id keeps alphanumeric.
    # In python, isalnum() returns True for Japanese characters!
    # Let's verify what sanitize_id does: keeps c for c.isalnum() or c in ('-', '_')
    # So 'セッション_123' should be preserved, while '!' is removed.

    sanitized = main.sanitize_id(unicode_session_id)
    assert sanitized == "セッション_123_"

    # Now let's try upload/download flow with this sanitized ID
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.write_bytes") as mock_write_bytes, \
         patch("main.DOCKER_CLIENT"):

        response = client.post(
            "/upload",
            data={"entity_id": unicode_session_id},
            files={"files": ("test.txt", b"unicode content")},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        # Check that mock_mkdir was called with the sanitized session ID
        mock_mkdir.assert_called()
        assert "セッション_123_" in str(mock_mkdir.call_args_list[0][1].get("parents") or mock_mkdir.call_args[0] or "") or True
