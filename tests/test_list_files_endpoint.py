import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    # Clear mappings before each test to ensure isolation
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

@patch("main.kernel_manager.list_files")
def test_list_files_success(mock_list_files):
    # Mock return value for list_files
    expected_files = ["data.csv", "script.py"]
    mock_list_files.return_value = expected_files

    session_id = "test_session_123"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    json_response = response.json()
    assert isinstance(json_response, list)
    assert len(json_response) == len(expected_files)
    for i, f in enumerate(expected_files):
        assert json_response[i]["filename"] == f
        assert json_response[i]["fileId"] == "" # No mapping yet
    mock_list_files.assert_called_once_with(session_id)

@patch("main.kernel_manager.list_files")
def test_list_files_with_mappings(mock_list_files):
    # Setup mappings
    nanoid_session = "nanoid_session_abc"
    real_session = "real_uuid_123"
    filename = "result.png"
    nanoid_file = "nanoid_file_xyz"

    with kernel_manager.lock:
        kernel_manager.nanoid_to_session[nanoid_session] = real_session
        kernel_manager.session_to_nanoid[real_session] = nanoid_session
        kernel_manager.file_id_map[nanoid_session] = {nanoid_file: filename}

    mock_list_files.return_value = [filename]

    # Test using nanoid session ID
    response = client.get(
        f"/files/{nanoid_session}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["filename"] == filename
    assert data[0]["fileId"] == nanoid_file
    assert data[0]["id"] == nanoid_file

    # Verify it called list_files with the REAL session ID
    mock_list_files.assert_called_once_with(real_session)

@patch("main.kernel_manager.list_files")
def test_list_files_sanitization(mock_list_files):
    mock_list_files.return_value = []

    # Test sanitization of special characters (excluding # which starts a fragment)
    session_id = "session!@$123.dot"
    sanitized_id = "session123dot"

    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    mock_list_files.assert_called_once_with(sanitized_id)

@patch("main.kernel_manager.list_files")
def test_list_files_unauthorized(mock_list_files):
    session_id = "test_session_123"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 401
    assert not mock_list_files.called

@patch("main.kernel_manager.list_files")
def test_list_files_empty(mock_list_files):
    mock_list_files.return_value = []

    session_id = "empty_session"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == []
    mock_list_files.assert_called_once_with(session_id)
