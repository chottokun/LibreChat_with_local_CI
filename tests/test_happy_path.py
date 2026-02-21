import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import main

# Note: We don't mock sys.modules anymore to avoid breaking other tests.

@patch('main.kernel_manager')
def test_run_code_success(mock_kernel_manager):
    # Setup mock for execute_code
    mock_kernel_manager.execute_code.return_value = {
        "stdout": "hello world\n",
        "stderr": "",
        "exit_code": 0
    }
    # Mock list_files to return an empty list, otherwise it returns a MagicMock
    # which causes ResponseValidationError in FastAPI
    mock_kernel_manager.list_files.return_value = []
    
    # Mock lock because run_code uses it now (PR #40)
    mock_kernel_manager.lock = MagicMock()
    mock_kernel_manager.session_to_nanoid = {}
    mock_kernel_manager.nanoid_to_session = {}
    mock_kernel_manager.file_id_map = {}

    client = TestClient(main.app)

    response = client.post(
        "/run/exec",
        headers={"X-API-Key": main.API_KEY},
        json={"code": "print('hello world')", "session_id": "test_session"}
    )

    assert response.status_code == 200
    assert response.json()["stdout"] == "hello world\n"
    assert response.json()["exit_code"] == 0
    assert "session_id" in response.json()
