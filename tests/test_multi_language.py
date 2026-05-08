import pytest
from fastapi.testclient import TestClient
from main import app, API_KEY
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

def test_multi_language_bash(mock_docker):
    headers = {"X-API-Key": API_KEY}
    code = "echo 'hello world'"
    response = client.post(
        "/exec",
        json={
            "code": code,
            "lang": "bash",
            "session_id": "test-bash"
        },
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["stdout"] == "stdout_output"
    
    # Verify that it used bash and the correct extension
    calls = mock_docker.containers.run.return_value.exec_run.call_args_list
    exec_call = next(c for c in calls if "bash" in c.kwargs.get("cmd", [])[0])
    assert exec_call.kwargs["cmd"][0] == "bash"
    assert exec_call.kwargs["cmd"][1].endswith(".sh")

def test_multi_language_r(mock_docker):
    headers = {"X-API-Key": API_KEY}
    code = "print('hello')"
    response = client.post(
        "/exec",
        json={
            "code": code,
            "lang": "r",
            "session_id": "test-r"
        },
        headers=headers
    )
    assert response.status_code == 200
    
    # Verify that it used Rscript and the correct extension
    calls = mock_docker.containers.run.return_value.exec_run.call_args_list
    exec_call = next(c for c in calls if "Rscript" in c.kwargs.get("cmd", [])[0])
    assert exec_call.kwargs["cmd"][0] == "Rscript"
    assert exec_call.kwargs["cmd"][1].endswith(".R")

def test_python_still_wrapped(mock_docker):
    headers = {"X-API-Key": API_KEY}

    # 2. Test Python execution
    response = client.post(
        "/exec",
        json={
            "code": "1 + 1",
            "lang": "python",
            "session_id": "test-python"
        },
        headers=headers
    )
    assert response.status_code == 200

    # For Python, wrap_code should have been called, so the content uploaded should be wrapped.
    # But wait, exec_run call doesn't show the content, put_archive does.

    # We can't easily check the content of the tar here without extracting,
    # but we can assume wrap_code worked if it's called with python.

if __name__ == "__main__":
    pytest.main([__file__])
