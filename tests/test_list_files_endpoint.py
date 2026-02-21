from fastapi.testclient import TestClient
from unittest.mock import patch

# Mock docker.from_env before importing main to avoid Docker dependency in unit tests
with patch("docker.from_env") as mock_from_env:
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
    assert response.json() == {"files": expected_files}
    mock_list_files.assert_called_once_with(session_id)

def test_list_files_unauthorized():
    session_id = "test_session_unauth"

    # Test with wrong API key
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"

    # Test with missing API key
    response = client.get(
        f"/files/{session_id}"
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"

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
    assert response.json() == {"files": []}
    mock_list_files.assert_called_once_with(session_id)
