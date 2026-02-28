from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
import main
from main import app, API_KEY

client = TestClient(app)

def test_download_file_not_found_volume_mode():
    # Test 404 when RCE_DATA_DIR_HOST is set and file doesn't exist on host
    with patch("main.RCE_DATA_DIR_HOST", "/some/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/some/internal/path"), \
         patch("os.path.exists", return_value=False):

        response = client.get(
            "/api/files/code/download/test_session/nonexistent.txt",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "File not found"

def test_download_file_not_found_standard_mode():
    # Test 404 when RCE_DATA_DIR_HOST is None and kernel_manager.download_file fails
    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch("main.kernel_manager.download_file") as mock_download:

        mock_download.side_effect = HTTPException(status_code=404, detail="File not found")

        response = client.get(
            "/api/files/code/download/test_session/nonexistent.txt",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "File not found"
