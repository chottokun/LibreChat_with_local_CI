import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app, kernel_manager

client = TestClient(app)

def test_path_traversal_vulnerability(tmp_path):
    # Setup: Use a temporary directory for RCE_DATA_DIR_INTERNAL
    test_data_dir = str(tmp_path / "sessions")
    os.makedirs(test_data_dir, exist_ok=True)
    
    # Mock DOCKER_CLIENT to avoid pulling images
    mock_docker = MagicMock()
    
    with patch("main.RCE_DATA_DIR_INTERNAL", test_data_dir), \
         patch("main.RCE_DATA_DIR_HOST", test_data_dir), \
         patch("main.API_KEY", "testkey"), \
         patch("main.DOCKER_CLIENT", mock_docker):
        
        headers = {"X-API-Key": "testkey"}
        session_id = "traversal-test"
        
        # 1. Attempt to upload a file with a malicious path
        malicious_filename = "../../etc/passwd"
        files = [("files", (malicious_filename, b"fake passwd content", "text/plain"))]
        
        response = client.post(
            "/upload",
            data={"entity_id": session_id},
            files=files,
            headers=headers
        )
        assert response.status_code == 200
        file_id = response.json()["files"][0]["fileId"]
        
        # Check the mapping directly
        with kernel_manager.lock:
            stored_filename = kernel_manager.file_id_map.get(session_id, {}).get(file_id)
            print(f"Stored filename: {stored_filename}")
            
        # 2. Try to download the file using the returned file_id
        download_url = f"/download/{session_id}/{file_id}"
        client.get(download_url, headers=headers)
        
        # The stored filename should be sanitized!
        # If it's vulnerable, stored_filename will be "../../etc/passwd"
        assert os.path.basename(stored_filename) == stored_filename, f"VULNERABILITY: Stored filename '{stored_filename}' contains path segments!"

if __name__ == "__main__":
    pytest.main([__file__])
