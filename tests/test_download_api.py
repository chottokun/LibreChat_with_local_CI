import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi.responses import Response, FileResponse
import main
from main import app, API_KEY

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_km():
    main.kernel_manager.active_kernels = {}
    main.kernel_manager.nanoid_to_session = {}
    main.kernel_manager.session_to_nanoid = {}
    main.kernel_manager.file_id_map = {}

@patch("main.kernel_manager.download_file")
def test_download_session_file_standard_mode(mock_download):
    """Test download in standard mode (Docker API fallback)."""
    mock_content = b"test content"
    mock_mtime = 123456789.0
    mock_download.return_value = (mock_content, mock_mtime)

    with patch("main.RCE_DATA_DIR_HOST", None):
        response = client.get(
            "/download/session123/test.txt",
            headers={"X-API-Key": API_KEY}
        )

    assert response.status_code == 200
    assert response.content == mock_content
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "inline; filename=\"test.txt\"; filename*=utf-8''test.txt" in response.headers["content-disposition"]
    mock_download.assert_called_once_with("session123", "test.txt")

@patch("main.os.path.exists")
@patch("main.FileResponse")
def test_download_session_file_advanced_mode(mock_file_response, mock_exists):
    """Test download in advanced mode (volume mount)."""
    mock_exists.return_value = True
    mock_file_response.return_value = Response(content=b"file content")

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"):
        response = client.get(
            "/download/session123/test.txt",
            headers={"X-API-Key": API_KEY}
        )

    assert response.status_code == 200
    mock_file_response.assert_called_once()
    args, kwargs = mock_file_response.call_args
    assert kwargs["path"] == "/internal/path/session123/test.txt"
    assert kwargs["media_type"] == "text/plain"

def test_download_file_query_params():
    """Test download via query parameters."""
    with patch("main.download_session_file") as mock_download_session_file:
        mock_download_session_file.return_value = Response(content=b"ok")
        response = client.get(
            "/download",
            params={"session_id": "session123", "filename": "test.txt"},
            headers={"X-API-Key": API_KEY}
        )

    assert response.status_code == 200
    mock_download_session_file.assert_called_once()
    # Check that it was called with expected arguments
    args = mock_download_session_file.call_args[0]
    assert args[0] == "session123"
    assert args[1] == "test.txt"

@patch("main.kernel_manager.download_file")
def test_download_nanoid_resolution(mock_download):
    """Test resolution of nanoid session ID and file ID."""
    main.kernel_manager.nanoid_to_session["nanoid123"] = "real-uuid-456"
    main.kernel_manager.file_id_map["nanoid123"] = {"file-id-789": "actual_file.py"}

    mock_download.return_value = (b"print('hello')", 123.0)

    with patch("main.RCE_DATA_DIR_HOST", None):
        response = client.get(
            "/download/nanoid123/file-id-789",
            headers={"X-API-Key": API_KEY}
        )

    assert response.status_code == 200
    mock_download.assert_called_once_with("real-uuid-456", "actual_file.py")
    assert "filename=\"actual_file.py\"" in response.headers["content-disposition"]

@patch("main.kernel_manager.download_file")
def test_download_mime_types(mock_download):
    """Test MIME type detection and disposition."""
    mock_download.return_value = (b"a,b,c", 123.0)

    with patch("main.RCE_DATA_DIR_HOST", None):
        # CSV should be text/plain and inline
        response = client.get(
            "/download/s/data.csv",
            headers={"X-API-Key": API_KEY}
        )
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert response.headers["content-disposition"].startswith("inline")

        # Binary file should be application/octet-stream and attachment
        mock_download.return_value = (b"\x00\x01", 123.0)
        response = client.get(
            "/download/s/data.bin",
            headers={"X-API-Key": API_KEY}
        )
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment")

@patch("main.kernel_manager.download_file")
def test_download_non_ascii_filename(mock_download):
    """Test Content-Disposition encoding for non-ASCII filenames."""
    filename = "テスト"
    mock_download.return_value = (b"content", 123.0)

    with patch("main.RCE_DATA_DIR_HOST", None):
        response = client.get(
            f"/download/s/{filename}",
            headers={"X-API-Key": API_KEY}
        )

    assert response.status_code == 200
    # UTF-8 encoded "テスト" is %E3%83%86%E3%82%B9%E3%83%88
    expected_encoded = "%E3%83%86%E3%82%B9%E3%83%88"
    assert f"filename*=utf-8''{expected_encoded}" in response.headers["content-disposition"]
    # safe_filename_ascii should be "file" since all chars are non-ascii
    assert 'filename="file"' in response.headers["content-disposition"]

def test_download_unauthorized():
    """Test download without valid API key."""
    response = client.get("/download/s/f", headers={"X-API-Key": "invalid"})
    assert response.status_code == 401
