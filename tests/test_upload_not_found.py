import pytest
import docker
import logging
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app, API_KEY, kernel_manager

client = TestClient(app)

def test_upload_container_not_found(caplog):
    """
    Verifies the behavior when docker.errors.NotFound is raised during upload.
    Now it should return 404.
    """
    with patch.object(kernel_manager, 'get_or_create_container', side_effect=docker.errors.NotFound("Container not found")):
        with caplog.at_level(logging.ERROR):
            response = client.post(
                "/upload",
                headers={"X-API-Key": API_KEY},
                data={"session_id": "test-session-not-found"},
                files=[("files", ("test.txt", b"content"))]
            )

            # Now it should return 404
            assert response.status_code == 404
            assert "Session not found" in response.json()["detail"]
            # Check for the log message without assuming the exact session ID format
            assert "Container not found for session" in caplog.text
            assert "during upload" in caplog.text

def test_upload_generic_exception_in_km(caplog):
    """
    Verifies behavior when a generic Exception is raised during upload_file.
    """
    with patch.object(kernel_manager, 'get_or_create_container', side_effect=Exception("Something went wrong")):
        with caplog.at_level(logging.ERROR):
            response = client.post(
                "/upload",
                headers={"X-API-Key": API_KEY},
                data={"session_id": "test-session-error"},
                files=[("files", ("test.txt", b"content"))]
            )

            # This should still return 500, but from the new handler in upload_file
            assert response.status_code == 500
            assert "Something went wrong" in response.json()["detail"]
            assert "Error uploading file: Something went wrong" in caplog.text
