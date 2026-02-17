import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import docker.errors
from main import KernelManager

def test_start_new_container_failure(docker_client):
    """
    Test that KernelManager.start_new_container raises HTTPException(500)
    when DOCKER_CLIENT.containers.run fails.
    """
    km = KernelManager()
    session_id = "test_session_fail"

    # Configure the mock to raise an exception when containers.run is called
    docker_client.containers.run.side_effect = Exception("Docker connection failed")

    with pytest.raises(HTTPException) as excinfo:
        km.start_new_container(session_id)

    assert excinfo.value.status_code == 500
    assert "Failed to start sandbox: Docker connection failed" in excinfo.value.detail

    # Verify it was called with expected arguments
    docker_client.containers.run.assert_called_once()

def test_start_new_container_success(docker_client):
    mock_container = MagicMock()
    mock_container.id = "new_container_id"
    docker_client.containers.run.return_value = mock_container

    km = KernelManager()
    km.active_kernels = {}
    container = km.start_new_container("test_session_success")

    assert container.id == "new_container_id"
    assert km.active_kernels["test_session_success"] == "new_container_id"

def test_get_or_create_container_existing_running(docker_client):
    km = KernelManager()
    km.active_kernels = {"session1": "container1"}

    mock_container = MagicMock()
    mock_container.status = "running"
    docker_client.containers.get.return_value = mock_container

    container = km.get_or_create_container("session1")

    assert container == mock_container
    docker_client.containers.get.assert_called_with("container1")

def test_get_or_create_container_existing_stopped(docker_client):
    km = KernelManager()
    km.active_kernels = {"session1": "container1"}

    mock_container = MagicMock()
    mock_container.status = "stopped"
    docker_client.containers.get.return_value = mock_container

    container = km.get_or_create_container("session1")

    assert container == mock_container
    mock_container.start.assert_called_once()

def test_get_or_create_container_not_found(docker_client):
    km = KernelManager()
    km.active_kernels = {"session1": "container1"}

    docker_client.containers.get.side_effect = docker.errors.NotFound("Not found")

    # Mock start_new_container to avoid actual docker call
    with patch.object(km, 'start_new_container') as mock_start_new:
        mock_start_new.return_value = MagicMock()
        km.get_or_create_container("session1")

        assert "session1" not in km.active_kernels
        mock_start_new.assert_called_once_with("session1")

def test_execute_code_success():
    km = KernelManager()
    mock_container = MagicMock()
    mock_container.exec_run.return_value = MagicMock(output=b"hello\n", exit_code=0)

    with patch.object(km, 'get_or_create_container', return_value=mock_container):
        result = km.execute_code("session1", "print('hello')")

        assert result["stdout"] == "hello\n"
        assert result["exit_code"] == 0
        mock_container.exec_run.assert_called_once()

def test_execute_code_exception():
    km = KernelManager()
    mock_container = MagicMock()
    mock_container.exec_run.side_effect = Exception("Exec failed")

    with patch.object(km, 'get_or_create_container', return_value=mock_container):
        result = km.execute_code("session1", "print('hello')")

        assert "error" in result
        assert result["error"] == "Exec failed"
