import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app, API_KEY, kernel_manager
import main

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    # Clear mappings before each test
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_download_file_query_success():
    """Test successful file download using query parameters via /download."""
    session_id = "test_session"
    filename = "test.txt"
    content = b"hello world"
    mtime = 12345.0

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", return_value=(content, mtime)) as mock_download:

        response = client.get(
            "/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        assert "text/plain" in response.headers["content-type"]
        assert f"filename=\"{filename}\"" in response.headers["content-disposition"]
        mock_download.assert_called_once_with(session_id, filename)

def test_download_run_file_query_success():
    """Test successful file download using query parameters via /run/download."""
    session_id = "test_session_run"
    filename = "run.txt"
    content = b"run output"
    mtime = 67890.0

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", return_value=(content, mtime)) as mock_download:

        response = client.get(
            "/run/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        mock_download.assert_called_once_with(session_id, filename)

def test_download_file_query_unauthorized():
    """Test 401 response when API key is missing or invalid."""
    response = client.get(
        "/download",
        params={"session_id": "s", "filename": "f.txt"},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401

def test_download_file_query_missing_params():
    """Test 422 response when session_id or filename is missing."""
    # Missing filename
    response = client.get(
        "/download",
        params={"session_id": "s"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

    # Missing session_id
    response = client.get(
        "/download",
        params={"filename": "f.txt"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

def test_download_file_query_not_found():
    """Test 404 response when the file does not exist."""
    from fastapi import HTTPException

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", side_effect=HTTPException(status_code=404, detail="File not found")):

        response = client.get(
            "/download",
            params={"session_id": "s", "filename": "missing.txt"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "File not found"

def test_download_session_file_path_params_success():
    """Test successful download using path parameters."""
    session_id = "path_session"
    filename = "path_file.png"
    content = b"fake-png-content"
    mtime = 11111.0

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", return_value=(content, mtime)):

        response = client.get(
            f"/download/{session_id}/{filename}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        assert "image/png" in response.headers["content-type"]
        assert "inline" in response.headers["content-disposition"]

def test_download_session_file_advanced_mode_success(tmp_path):
    """Test successful download when RCE_DATA_DIR_HOST is set (Advanced Mode)."""
    session_id = "adv_session"
    filename = "adv_file.txt"
    content = b"advanced mode content"

    # Setup mock data directory
    internal_dir = tmp_path / "data"
    session_dir = internal_dir / session_id
    session_dir.mkdir(parents=True)
    file_path = session_dir / filename
    file_path.write_bytes(content)

    with patch("main.RCE_DATA_DIR_HOST", "some/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", str(internal_dir)):

        response = client.get(
            "/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
