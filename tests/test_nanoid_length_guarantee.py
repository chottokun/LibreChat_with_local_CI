import pytest
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY
from unittest.mock import patch, MagicMock

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_docker_for_guarantee_test():
    with patch("main.DOCKER_CLIENT") as mock_docker:
        mock_container = MagicMock()
        mock_docker.containers.run.return_value = mock_container
        yield mock_docker

def test_nanoid_length_guarantee_upload_and_exec():
    """
    Verify that providing any length of session ID (shorter, longer, or containing spaces/special chars)
    to both /upload and /exec will guarantee that the returned session_id is a 21-character Nanoid,
    and that both map to the same internal session.
    """
    headers = {"X-API-Key": API_KEY}

    # Reset mapping
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}

    short_sid = "short"
    files = [("files", ("test.txt", b"hello", "text/plain"))]

    # 1. Upload to short session ID
    response = client.post(
        "/upload",
        headers=headers,
        data={"entity_id": short_sid},
        files=files
    )
    assert response.status_code == 200
    upload_returned_sid = response.json()["session_id"]

    assert len(upload_returned_sid) == 21

    # Verify mapping
    real_sid_from_input, _ = kernel_manager.get_or_create_session_mapping(short_sid)
    real_sid_from_returned, _ = kernel_manager.get_or_create_session_mapping(upload_returned_sid)
    assert real_sid_from_input == real_sid_from_returned

    # 2. Exec with long session ID
    long_sid = "this-is-a-very-long-session-id-that-is-not-21-characters"

    # Mock container run exec response
    with patch.object(kernel_manager, "execute_code") as mock_execute:
        mock_execute.return_value = {"stdout": "executed", "stderr": "", "exit_code": 0}

        resp = client.post(
            "/exec",
            headers=headers,
            json={"code": "print(1)", "session_id": long_sid}
        )
        assert resp.status_code == 200
        exec_returned_sid = resp.json()["session_id"]
        assert len(exec_returned_sid) == 21

        # Verify mapping
        real_sid_long_input, _ = kernel_manager.get_or_create_session_mapping(long_sid)
        real_sid_long_returned, _ = kernel_manager.get_or_create_session_mapping(exec_returned_sid)
        assert real_sid_long_input == real_sid_long_returned
