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

    # 1. Test /upload with a non-21-char session ID
    test_sid_upload = "test-session-upload"
    files = [("files", ("test.txt", b"hello", "text/plain"))]
    response_upload = client.post(
        "/upload",
        data={"entity_id": test_sid_upload},
        files=files,
        headers=headers
    )
    assert response_upload.status_code == 200
    returned_sid_upload = response_upload.json()["session_id"]
    # Guaranteed to be a 21-char Nanoid
    assert len(returned_sid_upload) == 21

    # 2. Test /exec with another non-21-char session ID (using spaces to verify sanitization and nanoid translation)
    test_sid_exec = "test session exec"
    response_exec = client.post(
        "/exec",
        json={
            "code": "print('hello')",
            "session_id": test_sid_exec
        },
        headers=headers
    )
    assert response_exec.status_code == 200
    returned_sid_exec = response_exec.json()["session_id"]

    # Guaranteed to be a 21-char Nanoid
    assert len(returned_sid_exec) == 21

    # Verify that the mapped UUID is resolved consistently when the resolved nanoid is provided
    # (Checking that resolved_download_ids maps returned_sid_exec and returned_sid_upload correctly)
    real_sid_up, filename_up = kernel_manager.resolve_download_ids(returned_sid_upload, "test.txt")
    assert filename_up == "test.txt"
    assert real_sid_up != returned_sid_upload # resolved to internal uuid

    real_sid_ex, _ = kernel_manager.resolve_download_ids(returned_sid_exec, "dummy")
    assert real_sid_ex != returned_sid_exec

if __name__ == "__main__":
    pytest.main([__file__])
