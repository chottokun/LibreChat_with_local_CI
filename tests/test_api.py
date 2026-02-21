import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import os

# Mock docker.from_env before importing main
with patch("docker.from_env") as mock_from_env:
    from main import app, API_KEY

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "docker-sandboxed"}

def test_run_code_unauthorized():
    response = client.post("/exec", json={"code": "print('hello')", "session_id": "test"}, headers={"X-API-Key": "wrong_key"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"

@patch("main.kernel_manager.execute_code")
@patch("main.kernel_manager.list_files")
def test_run_code_success(mock_list_files, mock_execute):
    mock_execute.return_value = {"stdout": "hello\n", "stderr": "", "exit_code": 0}
    mock_list_files.return_value = []

    response = client.post("/exec",
                           json={"code": "print('hello')", "session_id": "test_session"},
                           headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
    assert response.json()["stdout"] == "hello\n"
    assert response.json()["exit_code"] == 0
    mock_execute.assert_called_once_with("test_session", "print('hello')")

@patch("main.kernel_manager.execute_code")
@patch("main.kernel_manager.list_files")
def test_run_exec_success(mock_list_files, mock_execute):
    mock_execute.return_value = {"stdout": "exec_output", "stderr": "", "exit_code": 0}
    mock_list_files.return_value = []

    response = client.post("/run/exec",
                           json={"code": "print('exec')", "session_id": "test_session_exec"},
                           headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
    assert response.json()["stdout"] == "exec_output"
    mock_execute.assert_called_once_with("test_session_exec", "print('exec')")

@patch("main.kernel_manager.execute_code")
@patch("main.kernel_manager.list_files")
def test_run_code_no_session_id(mock_list_files, mock_execute):
    mock_execute.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}
    mock_list_files.return_value = []

    response = client.post("/exec",
                           json={"code": "print('hello')"},
                           headers={"X-API-Key": API_KEY})

    assert response.status_code == 200
    # The session_id is generated as a UUID, so we just check that execute_code was called
    mock_execute.assert_called_once()
    args, kwargs = mock_execute.call_args
    assert len(args[0]) > 0  # session_id generated

@patch("main.kernel_manager.list_files")
def test_auth_precedence_header_wins(mock_list_files):
    mock_list_files.return_value = []
    # Valid header, invalid query param -> should succeed
    response = client.get("/files/test", headers={"X-API-Key": API_KEY}, params={"api_key": "wrong_key"})
    assert response.status_code == 200

def test_auth_precedence_invalid_header_fails():
    # Invalid header, valid query param -> should fail 401
    # Because the header is present (not None), it's chosen as 'key', and then validated.
    response = client.get("/files/test", headers={"X-API-Key": "wrong_key"}, params={"api_key": API_KEY})
    assert response.status_code == 401

@patch("main.kernel_manager.list_files")
def test_auth_query_fallback_success(mock_list_files):
    mock_list_files.return_value = []
    # No header, valid query param -> should succeed
    response = client.get("/files/test", params={"api_key": API_KEY})
    assert response.status_code == 200
