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
        mock_exec_res_normal.output = b"[]"

        def side_effect(cmd, **kwargs):
            if kwargs.get("demux"):
                return mock_exec_res_demux
            return mock_exec_res_normal

        mock_container.exec_run.side_effect = side_effect
        mock_client.containers.run.return_value = mock_container
        yield mock_client

def test_respect_provided_sid_with_spaces(mock_docker):
    kernel_manager.nanoid_to_session = {}
    kernel_manager.session_to_nanoid = {}

    headers = {"X-API-Key": API_KEY}
    test_sid = "test session with spaces"

    response = client.post(
        "/exec",
        json={"code": "print('hello')", "session_id": test_sid},
        headers=headers
    )

    returned_sid = response.json()["session_id"]
    print(f"Provided: '{test_sid}'")
    print(f"Returned: '{returned_sid}'")

    assert returned_sid == test_sid
