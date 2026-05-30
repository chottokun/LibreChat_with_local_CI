import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from fastapi.responses import Response
from main import app, API_KEY

client = TestClient(app)

@patch("main.download_session_file")
def test_download_file_query_success(mock_download_session_file):
    """Test successful download via /download query parameters."""
    # Mock the return value of download_session_file
    mock_download_session_file.return_value = Response(content="test content", media_type="text/plain")

    session_id = "test_session_id"
    filename = "test_file.txt"

    response = client.get(
        "/download",
        params={"session_id": session_id, "filename": filename},
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    assert response.content == b"test content"
    mock_download_session_file.assert_called_once()
    # Check that it was called with the correct parameters
    args, kwargs = mock_download_session_file.call_args
    assert args[0] == session_id
    assert args[1] == filename

@patch("main.download_session_file")
def test_run_download_file_query_success(mock_download_session_file):
    """Test successful download via /run/download query parameters."""
    mock_download_session_file.return_value = Response(content="run test content", media_type="text/plain")

    session_id = "run_session_id"
    filename = "run_file.txt"

    response = client.get(
        "/run/download",
        params={"session_id": session_id, "filename": filename},
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    assert response.content == b"run test content"
    mock_download_session_file.assert_called_once()
    assert mock_download_session_file.call_args[0][0] == session_id
    assert mock_download_session_file.call_args[0][1] == filename

def test_download_file_query_unauthorized():
    """Test /download with invalid API key."""
    response = client.get(
        "/download",
        params={"session_id": "test", "filename": "test.txt"},
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 401

def test_download_file_query_missing_params():
    """Test /download with missing required query parameters."""
    # Missing filename
    response = client.get(
        "/download",
        params={"session_id": "test_session"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

    # Missing session_id
    response = client.get(
        "/download",
        params={"filename": "test.txt"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

@patch("main.download_session_file")
def test_download_file_query_not_found(mock_download_session_file):
    """Test /download when file is not found (mocking delegation)."""
    from fastapi import HTTPException
    mock_download_session_file.side_effect = HTTPException(status_code=404, detail="File not found")

    response = client.get(
        "/download",
        params={"session_id": "non_existent", "filename": "missing.txt"},
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"
