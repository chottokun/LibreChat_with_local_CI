import pytest
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

def test_download_session_file_endpoint_pathlib():
    """Verify download_session_file endpoint under volume-mount pathlib implementation."""
    client = TestClient(app)

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve") as mock_resolve, \
         patch("os.stat") as mock_os_stat, \
         patch("anyio.open_file") as mock_open_file:

        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 14
        mock_stat_result.st_mtime = 123456789.0
        mock_stat_result.st_mode = 33188  # regular file
        mock_os_stat.return_value = mock_stat_result

        # Mock async with anyio.open_file
        mock_file = MagicMock()
        mock_file.__aenter__.return_value = MagicMock(read=AsyncMock(return_value=b"volume content"))
        mock_open_file.return_value = mock_file

        # Mock resolve paths to make sure is_relative_to succeeds
        mock_resolve.side_effect = lambda *args, **kwargs: Path("/internal/path/session_uuid/test.txt")

        # Fake resolve_download_ids
        with patch.object(main.kernel_manager, "resolve_download_ids", return_value=("session_uuid", "test.txt")):
            response = client.get(
                "/download/session_uuid/test.txt",
                headers={"X-API-Key": main.API_KEY}
            )
            assert response.status_code == 200
            assert response.content == b"volume content"
