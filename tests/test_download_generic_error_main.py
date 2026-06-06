import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
import main
from main import app, API_KEY

client = TestClient(app)

@patch("main.RCE_DATA_DIR_HOST", "some/host/path")
@patch("os.path.exists")
def test_download_session_file_generic_exception_volume_mode(mock_exists, caplog):
    """
    Test that an unexpected exception during file existence check (volume mode)
    is caught, logged, and returns a 500 error.
    Targets main.py:977-979
    """
    # Force os.path.exists to raise an exception
    mock_exists.side_effect = Exception("Disk error")

    local_client = TestClient(app, raise_server_exceptions=False)
    response = local_client.get(
        "/download/test_session/test_file.txt",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error during file download"
    assert "Failed to download file test_file.txt from session test_session: Disk error" in caplog.text

@patch("main.RCE_DATA_DIR_HOST", None)
@patch("main.kernel_manager.download_file")
def test_download_session_file_generic_exception_docker_mode(mock_download, caplog):
    """
    Test that an unexpected exception during download_file (docker mode)
    is caught, logged, and returns a 500 error.
    Targets main.py:977-979
    """
    # Force kernel_manager.download_file to raise an exception
    mock_download.side_effect = Exception("Docker daemon crash")

    local_client = TestClient(app, raise_server_exceptions=False)
    response = local_client.get(
        "/download/test_session/test_file.txt",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error during file download"
    assert "Failed to download file test_file.txt from session test_session: Docker daemon crash" in caplog.text
