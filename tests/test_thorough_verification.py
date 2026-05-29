import asyncio
import pytest
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY
from unittest.mock import MagicMock, patch
import json
import io
import tarfile

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_km():
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}

def test_thorough_lifecycle_integration():
    """
    Integration test for the entire fixed flow:
    1. Upload multiple files using a NanoID.
    2. Verify Docker container labels (Persistence preparation).
    3. Recover from "restart" and verify mapping restoration.
    4. Execute code in multiple languages.
    5. Robust file listing and download.
    """
    headers = {"X-API-Key": API_KEY}
    nanoid = "thorough-test-nanoid"
    filename1 = "data.csv"
    filename2 = "script.py"

    # 1. & 2. Upload and Label Verification
    with patch("main.DOCKER_CLIENT") as mock_docker:
        mock_container = MagicMock()
        mock_docker.containers.run.return_value = mock_container

        # mock for list_files (which is called in run_code, or here after upload)
        mock_list_res = MagicMock()
        mock_list_res.exit_code = 0
        mock_list_res.output = (json.dumps([]).encode('utf-8'), b"")
        mock_container.exec_run.return_value = mock_list_res

        # Parallel upload test
        files = [
            ("files", (filename1, b"col1,col2\n1,2")),
            ("files", (filename2, b"print('hello')"))
        ]

        resp = client.post(
            "/upload",
            headers=headers,
            data={"entity_id": nanoid},
            files=files
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == nanoid
        assert len(data["files"]) == 2

        internal_uuid = kernel_manager.nanoid_to_session[nanoid]

        # Verify labels for persistence
        mock_docker.containers.run.assert_called_once()
        labels = mock_docker.containers.run.call_args.kwargs["labels"]
        assert labels["external_session_id"] == nanoid
        assert labels["session_id"] == internal_uuid

    # 3. Restart and Recovery
    kernel_manager.active_kernels = {}
    kernel_manager.nanoid_to_session = {}
    kernel_manager.session_to_nanoid = {}

    with patch("main.DOCKER_CLIENT") as mock_docker:
        mock_recovered_container = MagicMock()
        mock_recovered_container.labels = {
            "managed_by": "librechat-rce",
            "session_id": internal_uuid,
            "external_session_id": nanoid
        }
        mock_docker.containers.list.return_value = [mock_recovered_container]

        kernel_manager.recover_containers()
        assert nanoid in kernel_manager.nanoid_to_session
        assert kernel_manager.nanoid_to_session[nanoid] == internal_uuid

    # 4. Multi-language Execution
    with patch("main.DOCKER_CLIENT") as mock_docker:
        # Mock for execute_code (demux=True)
        mock_exec_res = MagicMock()
        mock_exec_res.exit_code = 0
        mock_exec_res.output = (b"executed", b"")

        # Mock for list_files (demux=True)
        mock_list_res = MagicMock()
        mock_list_res.exit_code = 0
        mock_list_res.output = (json.dumps([]).encode('utf-8'), b"")

        def side_effect(cmd, **kwargs):
            if "listdir" in cmd[-1]:
                return mock_list_res
            return mock_exec_res

        mock_recovered_container.exec_run.side_effect = side_effect

        # Bash execution
        resp_bash = client.post(
            "/exec",
            headers=headers,
            json={"code": "echo 123", "lang": "bash", "session_id": nanoid}
        )
        assert resp_bash.status_code == 200

        # Check that bash was used
        bash_calls = [c for c in mock_recovered_container.exec_run.call_args_list if "bash" in c.kwargs.get("cmd", [])]
        assert len(bash_calls) > 0

        # R execution
        resp_r = client.post(
            "/exec",
            headers=headers,
            json={"code": "print(1)", "lang": "r", "session_id": nanoid}
        )
        assert resp_r.status_code == 200
        r_calls = [c for c in mock_recovered_container.exec_run.call_args_list if "Rscript" in c.kwargs.get("cmd", [])]
        assert len(r_calls) > 0

    # 5. Robust File Listing (JSON)
    with patch("main.DOCKER_CLIENT") as mock_docker:
        special_filename = "ファイル 名.txt"
        file_list = [filename1, filename2, special_filename]

        mock_list_res = MagicMock()
        mock_list_res.exit_code = 0
        mock_list_res.output = (json.dumps(file_list).encode('utf-8'), b"")
        mock_recovered_container.exec_run.side_effect = None
        mock_recovered_container.exec_run.return_value = mock_list_res

        resp = client.get(f"/files/{nanoid}", headers=headers)
        assert resp.status_code == 200
        returned_files = [f["filename"] for f in resp.json()]
        for f in file_list:
            assert f in returned_files

def test_parallel_upload_consistency():
    """Verifies that parallel uploads don't cause race conditions in mapping."""
    headers = {"X-API-Key": API_KEY}
    nanoid = "race-test-id"

    with patch("main.DOCKER_CLIENT") as mock_docker:
        mock_container = MagicMock()
        mock_docker.containers.run.return_value = mock_container

        # mock for list_files
        mock_list_res = MagicMock()
        mock_list_res.exit_code = 0
        mock_list_res.output = (json.dumps([]).encode('utf-8'), b"")
        mock_container.exec_run.return_value = mock_list_res

        # Simulate many files
        files = [("files", (f"file_{i}.txt", b"data")) for i in range(20)]

        resp = client.post(
            "/upload",
            headers=headers,
            data={"entity_id": nanoid},
            files=files
        )
        assert resp.status_code == 200
        assert len(resp.json()["files"]) == 20

        # Verify internal mapping is single
        assert len(kernel_manager.nanoid_to_session) == 1
        assert nanoid in kernel_manager.nanoid_to_session

if __name__ == "__main__":
    pytest.main([__file__])
