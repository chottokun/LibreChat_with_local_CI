import pytest
import logging
import os
from unittest.mock import MagicMock, patch
import docker

# Mock docker.from_env and set env vars before importing main to prevent side effects
with patch("docker.from_env") as mock_from_env:
    os.environ.setdefault("LIBRECHAT_CODE_API_KEY", "dummy-key")
    os.environ.setdefault("DISABLE_CODE_API_AUTH", "true")
    from main import KernelManager

@pytest.fixture
def kernel_manager():
    return KernelManager()

def test_execute_code_cleanup_logging_on_docker_exception(kernel_manager, caplog):
    """Test that a warning is logged when a DockerException occurs during cleanup."""
    session_id = "test_cleanup_log_session"
    code = "print('hello')"

    mock_container = MagicMock()
    # Mock exec_run to raise a DockerException during cleanup
    mock_container.exec_run.side_effect = docker.errors.DockerException("Cleanup failure")

    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (b"hello\n", b"")

    with patch.object(kernel_manager, 'get_or_create_container', return_value=mock_container):
        with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res):
            with caplog.at_level(logging.WARNING):
                result = kernel_manager.execute_code(session_id, code)

                assert result["stdout"] == "hello\n"

                # Verify warning log
                assert "Failed to remove temporary file" in caplog.text
                assert session_id in caplog.text

def test_execute_code_cleanup_logging_on_generic_exception(kernel_manager, caplog):
    """Test that a warning is logged when a generic Exception occurs during cleanup."""
    session_id = "test_cleanup_log_generic_session"
    code = "print('hello')"

    mock_container = MagicMock()
    # Mock exec_run to raise a generic Exception during cleanup
    mock_container.exec_run.side_effect = RuntimeError("Generic cleanup failure")

    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (b"hello\n", b"")

    with patch.object(kernel_manager, 'get_or_create_container', return_value=mock_container):
        with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res):
            with caplog.at_level(logging.WARNING):
                result = kernel_manager.execute_code(session_id, code)

                assert result["stdout"] == "hello\n"

                # Verify warning log
                assert "Failed to remove temporary file" in caplog.text
                assert session_id in caplog.text
