from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app, API_KEY

client = TestClient(app)

@patch("main.kernel_manager.list_files")
def test_list_files_success(mock_list_files):
    # Mock return value for list_files
    expected_files = ["data.csv", "script.py", "output/results.json"]
    mock_list_files.return_value = expected_files

    session_id = "test_session_123"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    json_response = response.json()
    assert isinstance(json_response, list)
    assert len(json_response) == 3
    assert json_response[0]["filename"] == "data.csv"
    assert "fileId" in json_response[0]

@patch("main.kernel_manager.list_files")
def test_list_files_unauthorized(mock_list_files):
    session_id = "test_session_123"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 401

@patch("main.kernel_manager.list_files")
def test_list_files_empty(mock_list_files):
    # Mock return value for an empty session
    mock_list_files.return_value = []

    session_id = "empty_session"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == []
