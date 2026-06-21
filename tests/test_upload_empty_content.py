import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch
import main
from main import app, API_KEY, kernel_manager

client = TestClient(app)

def test_upload_file_empty_content():
    """
    Test that upload_file raises a 400 HTTPException if content is empty.
    """
    # Mock resolve_session_id to avoid other issues
    with patch.object(kernel_manager, 'get_or_create_container') as mock_get_container:
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.upload_file(
                session_id="test-session",
                filename="empty.txt",
                content=b"",
                external_session_id=None
            )

        assert excinfo.value.status_code == 400
        assert excinfo.value.detail == "File content is empty"
        # Ensure it didn't even try to get/create a container
        mock_get_container.assert_not_called()

def test_api_upload_empty_file():
    """
    Test that the /upload endpoint returns 400 if an empty file is uploaded.
    """
    # We need to mock kernel_manager.upload_file or it might fail on sandbox creation
    # But actually, our change makes it raise HTTPException BEFORE sandbox creation

    response = client.post(
        "/upload",
        headers={"X-API-Key": API_KEY},
        data={"session_id": "api-empty-test"},
        files=[("files", ("empty.txt", b""))]
    )

    assert response.status_code == 400
    assert "File content is empty" in response.json()["detail"]
