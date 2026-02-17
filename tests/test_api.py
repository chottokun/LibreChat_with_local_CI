import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app, API_KEY

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "docker-sandboxed"}

def test_run_code_unauthorized():
    response = client.post("/run", json={"code": "print(1)", "session_id": "test"})
    # FastAPI Security with APIKeyHeader(auto_error=True) returns 403 Forbidden
    # but let's check what it actually returns in this environment.
    assert response.status_code in [401, 403]

def test_run_code_invalid_key():
    response = client.post("/run", json={"code": "print(1)", "session_id": "test"}, headers={"X-API-Key": "wrong_key"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"

def test_run_code_success():
    with patch('main.kernel_manager.execute_code') as mock_exec:
        mock_exec.return_value = {"stdout": "1\n", "stderr": "", "exit_code": 0}

        response = client.post(
            "/run",
            json={"code": "print(1)", "session_id": "test_session"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.json() == {"stdout": "1\n", "stderr": "", "exit_code": 0}
        mock_exec.assert_called_once_with("test_session", "print(1)")

def test_run_code_no_session_id():
    with patch('main.kernel_manager.execute_code') as mock_exec:
        mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}

        response = client.post(
            "/run",
            json={"code": "print(1)"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        # Check that a session_id was generated (it's a UUID)
        args, _ = mock_exec.call_args
        assert len(args[0]) > 0
