import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    """Reset the kernel_manager state before each test."""
    with kernel_manager.lock:
        kernel_manager.active_kernels.clear()
        kernel_manager.nanoid_to_session.clear()
        kernel_manager.session_to_nanoid.clear()
        kernel_manager.file_id_map.clear()
    yield

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
    # The API returns a list of dictionaries with filename, fileId, and id
    json_response = response.json()
    assert isinstance(json_response, list)
    assert len(json_response) == len(expected_files)
    for i, f in enumerate(expected_files):
        assert json_response[i]["filename"] == f
    assert "fileId" in json_response[0]
    mock_list_files.assert_called_once_with(session_id, external_session_id=session_id)

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
    mock_list_files.assert_called_once_with(session_id, external_session_id=session_id)

@patch("main.kernel_manager.list_files")
def test_list_files_sanitization(mock_list_files):
    mock_list_files.return_value = []

    # Session ID with characters that should be sanitized
    # Using '$' which is valid in URL path but should be removed by sanitize_id
    session_id = "session$123"
    sanitized_id = "session123"

    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    # kernel_manager.list_files should be called with the sanitized session ID
    mock_list_files.assert_called_once_with(sanitized_id, external_session_id=sanitized_id)

@patch("main.kernel_manager.list_files")
def test_list_files_nanoid_resolution(mock_list_files):
    mock_list_files.return_value = []

    nanoid_session = "nanoid_session_id"
    internal_uuid = "uuid_session_id"

    # Manually map the nanoid to an internal UUID
    with kernel_manager.lock:
        kernel_manager.nanoid_to_session[nanoid_session] = internal_uuid
        kernel_manager.session_to_nanoid[internal_uuid] = nanoid_session

    response = client.get(
        f"/files/{nanoid_session}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    # kernel_manager.list_files should be called with the internal UUID,
    # but external_session_id should be the NanoID
    mock_list_files.assert_called_once_with(internal_uuid, external_session_id=nanoid_session)

@patch("main.kernel_manager.list_files")
def test_list_files_with_id_mapping(mock_list_files):
    session_id = "test_session"
    filenames = ["file1.txt", "file2.csv"]
    mock_list_files.return_value = filenames

    file_id_1 = "id_file_1"
    file_id_2 = "id_file_2"

    # Pre-populate file_id_map
    with kernel_manager.lock:
        kernel_manager.file_id_map[session_id] = {
            file_id_1: filenames[0],
            file_id_2: filenames[1]
        }

    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 2

    # Verify that the response includes the correct file IDs
    file1_entry = next(f for f in json_response if f["filename"] == "file1.txt")
    assert file1_entry["fileId"] == file_id_1
    assert file1_entry["id"] == file_id_1

    file2_entry = next(f for f in json_response if f["filename"] == "file2.csv")
    assert file2_entry["fileId"] == file_id_2
    assert file2_entry["id"] == file_id_2
