import pytest
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY
from unittest.mock import MagicMock, patch

client = TestClient(app)

@pytest.fixture
def mock_docker():
    with patch("main.DOCKER_CLIENT") as mock_client:
        mock_container = MagicMock()

        # mock for execute_code (demux=True)
        mock_exec_res_demux = MagicMock()
        mock_exec_res_demux.exit_code = 0
        mock_exec_res_demux.output = (b"stdout_output", b"stderr_output")

        # mock for list_files (demux=False)
        mock_exec_res_normal = MagicMock()
        mock_exec_res_normal.exit_code = 0
        mock_exec_res_normal.output = b"file1.txt\nfile2.txt"

        def side_effect(cmd, **kwargs):
            if kwargs.get("demux"):
                return mock_exec_res_demux
            return mock_exec_res_normal

        mock_container.exec_run.side_effect = side_effect
        mock_client.containers.run.return_value = mock_container
        yield mock_client

def test_session_id_mapping_consistency(mock_docker):
    # Reset kernel manager state
    kernel_manager.active_kernels = {}
    kernel_manager.nanoid_to_session = {}
    kernel_manager.session_to_nanoid = {}
    kernel_manager.file_id_map = {}

    headers = {"X-API-Key": API_KEY}

    # 1. Test /upload with a new session ID
    test_sid_upload = "test-session-upload"
    files = [("files", ("test.txt", b"hello", "text/plain"))]
    response_upload = client.post(
        "/upload",
        data={"entity_id": test_sid_upload},
        files=files,
        headers=headers
    )
    assert response_upload.status_code == 200
    # In /upload, it should respect the provided sid if it's the first time seeing it
    assert response_upload.json()["session_id"] == test_sid_upload

    # 2. Test /exec with a new session ID
    test_sid_exec = "test-session-exec"
    response_exec = client.post(
        "/exec",
        json={
            "code": "print('hello')",
            "session_id": test_sid_exec
        },
        headers=headers
    )
    assert response_exec.status_code == 200
    returned_sid = response_exec.json()["session_id"]

    print(f"Provided SID for /exec: {test_sid_exec}")
    print(f"Returned SID from /exec: {returned_sid}")

    assert returned_sid == test_sid_exec, "Now /exec should respect provided SID for new sessions"

if __name__ == "__main__":
    pytest.main([__file__])
