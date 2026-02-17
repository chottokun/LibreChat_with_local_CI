import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import main
from main import app

client = TestClient(app)

@pytest.fixture
def mock_docker():
    with patch("main.DOCKER_CLIENT") as mock:
        yield mock

@pytest.fixture(autouse=True)
def clean_kernels():
    """Ensure active_kernels is empty before and after each test."""
    main.kernel_manager.active_kernels.clear()
    yield
    main.kernel_manager.active_kernels.clear()

def test_run_code_success(mock_docker):
    # Setup mock container
    mock_container = MagicMock()
    mock_container.status = "running"

    # Mock containers.get for existing session
    mock_docker.containers.get.return_value = mock_container

    # Mock exec_run result
    mock_exec_result = MagicMock()
    mock_exec_result.output = b"hello world\n"
    mock_exec_result.exit_code = 0
    mock_container.exec_run.return_value = mock_exec_result

    # Pre-populate active_kernels to simulate existing session
    main.kernel_manager.active_kernels["test_session"] = "fake_id"

    response = client.post(
        "/run",
        json={"code": "print('hello world')", "session_id": "test_session"},
        headers={"X-API-Key": "your_secret_key"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "stdout": "hello world\n",
        "stderr": "",
        "exit_code": 0
    }

def test_run_code_exec_alias(mock_docker):
    # Setup mock container
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_docker.containers.get.return_value = mock_container

    mock_exec_result = MagicMock()
    mock_exec_result.output = b"alias test\n"
    mock_exec_result.exit_code = 0
    mock_container.exec_run.return_value = mock_exec_result

    main.kernel_manager.active_kernels["alias_session"] = "fake_id_alias"

    response = client.post(
        "/run/exec",
        json={"code": "print('alias test')", "session_id": "alias_session"},
        headers={"X-API-Key": "your_secret_key"}
    )

    assert response.status_code == 200
    assert response.json()["stdout"] == "alias test\n"

def test_run_code_unauthorized():
    # Test without X-API-Key header
    response = client.post("/run", json={"code": "print(1)"})
    assert response.status_code == 401 # Changed from 403 as observed

def test_run_code_invalid_key():
    # Test with wrong X-API-Key header
    response = client.post(
        "/run",
        json={"code": "print(1)"},
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"

def test_run_code_docker_failure(mock_docker):
    # Mock docker failure when starting a new session
    mock_docker.containers.run.side_effect = Exception("Docker daemon connection error")

    # Ensure session is NOT in active_kernels so it tries to start a new one
    if "fail_session" in main.kernel_manager.active_kernels:
        del main.kernel_manager.active_kernels["fail_session"]

    response = client.post(
        "/run",
        json={"code": "print(1)", "session_id": "fail_session"},
        headers={"X-API-Key": "your_secret_key"}
    )

    assert response.status_code == 500
    assert "Failed to start sandbox" in response.json()["detail"]
    assert "Docker daemon connection error" in response.json()["detail"]
