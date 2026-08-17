import pytest
import concurrent.futures
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY, sanitize_id
from unittest.mock import patch, MagicMock

client = TestClient(app)
headers = {"X-API-Key": API_KEY}

INVALID_SESSION_VALUES = ["null", "undefined", "none", "NaN", "false", "0", "", "NULL", "Undefined"]

def test_sanitize_id_exhaustive_edge_cases():
    for val in INVALID_SESSION_VALUES:
        if val in ["false", "0"]:
            # "false" and "0" are valid alphanumeric strings if passed intentionally, but "null", "undefined", "none" return ""
            continue
        assert sanitize_id(val) == "", f"Expected sanitize_id('{val}') to return empty string"

def test_upload_and_list_files_with_null_session_id():
    with patch("main.DOCKER_CLIENT") as mock_docker:
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(exit_code=0, output=(b'["output.csv"]', b""))
        mock_docker.containers.run.return_value = mock_container

        # 1. Upload with session_id="null"
        files = [("files", ("output.csv", b"a,b,c\n1,2,3", "text/csv"))]
        res_up = client.post("/upload", data={"session_id": "null"}, files=files, headers=headers)
        assert res_up.status_code == 200
        up_data = res_up.json()

        # Verify top-level compatibility fields in upload response
        assert "fileId" in up_data
        assert "id" in up_data
        assert "filename" in up_data
        assert "name" in up_data
        assert "url" in up_data
        assert up_data["session_id"] != "null"
        assert len(up_data["session_id"]) == 21

        # 2. List files with session_id="null" (should fallback to LAST_UPLOADED_SESSION_ID)
        res_list = client.get("/files/null", headers=headers)
        assert res_list.status_code == 200
        list_data = res_list.json()
        assert isinstance(list_data, list)
        assert len(list_data) == 1
        assert list_data[0]["filename"] == "output.csv"
        assert list_data[0]["fileId"] == up_data["fileId"]

def test_exec_response_no_null_values():
    import main
    main.LAST_UPLOADED_SESSION_ID = None
    kernel_manager.active_kernels.clear()

    with patch("main.DOCKER_CLIENT") as mock_docker:
        mock_container = MagicMock()
        # Mock for execute_code demux=True -> (stdout_bytes, stderr_bytes)
        # Mock for list_files demux=True -> (json_file_list_bytes, None)
        def exec_side_effect(cmd, **kwargs):
            if isinstance(cmd, list) and len(cmd) >= 3 and "os.walk" in cmd[2]:
                return MagicMock(exit_code=0, output=(b"[]", b""))
            return MagicMock(exit_code=0, output=(b"printed output\n", b""))

        mock_container.exec_run.side_effect = exec_side_effect
        mock_docker.containers.run.return_value = mock_container

        res = client.post("/exec", json={"code": "print('hello')", "session_id": "undefined"}, headers=headers)
        assert res.status_code == 200
        data = res.json()

        # Verify all fields in CodeResponse are non-null
        assert data["stdout"] == "printed output\n"
        assert data["stderr"] == ""
        assert data["output"] == "printed output\n"
        assert data["result"] == "printed output\n"
        assert data["status"] == "success"
        assert isinstance(data["files"], list)
        assert isinstance(data["images"], list)
        assert data["session_id"] != ""
        assert None not in data.values()

def test_concurrent_null_session_uploads_and_downloads():
    with patch("main.DOCKER_CLIENT") as mock_docker, patch("main.kernel_manager.download_file") as mock_dl:
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(exit_code=0, output=(b"[]", b""))
        mock_docker.containers.run.return_value = mock_container
        mock_dl.return_value = (b"concurrent content", 123456789)

        def make_request(idx):
            files = [("files", (f"file_{idx}.txt", f"content_{idx}".encode(), "text/plain"))]
            res = client.post("/upload", data={"session_id": "null"}, files=files, headers=headers)
            return res.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(make_request, range(5)))

        for res_json in results:
            assert res_json["message"] == "success"
            assert res_json["session_id"] != "null"
            # Try download using fileId and session_id="null"
            dl_res = client.get(f"/download?session_id=null&file_id={res_json['fileId']}", headers=headers)
            assert dl_res.status_code == 200
            assert dl_res.content == b"concurrent content"

if __name__ == "__main__":
    pytest.main([__file__])
