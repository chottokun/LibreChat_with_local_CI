import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import os
import shutil
import tempfile
import main

@pytest.fixture
def temp_data_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

def test_upload_with_volume_mount(temp_data_dir):
    with patch('main.RCE_DATA_DIR_HOST', temp_data_dir), \
         patch('main.RCE_DATA_DIR_INTERNAL', temp_data_dir), \
         patch('main.DOCKER_CLIENT') as mock_docker:

        # Mock container run
        mock_container = MagicMock()
        mock_docker.containers.run.return_value = mock_container

        client = TestClient(main.app)
        session_id = "test-session-vol"

        response = client.post(
            "/upload",
            headers={"X-API-Key": main.API_KEY},
            data={"entity_id": session_id},
            files={"files": ("test.txt", b"hello volume")}
        )

        assert response.status_code == 200

        # The session ID might have been mapped to a UUID
        nanoid_session = response.json()["session_id"]
        internal_uuid = main.kernel_manager.nanoid_to_session.get(nanoid_session, nanoid_session)

        # Check if file exists in host temp dir
        expected_path = os.path.join(temp_data_dir, internal_uuid, "test.txt")
        assert os.path.exists(expected_path)
        with open(expected_path, "rb") as f:
            assert f.read() == b"hello volume"

        # Check if container was started with volumes
        mock_docker.containers.run.assert_called_once()
        args, kwargs = mock_docker.containers.run.call_args
        assert "volumes" in kwargs
        assert kwargs["volumes"] == {os.path.join(temp_data_dir, internal_uuid): {'bind': '/mnt/data', 'mode': 'rw'}}

def test_session_id_resolution_flow():
    with patch('main.kernel_manager') as mock_km:
        # Initial state: no mappings
        mock_km.nanoid_to_session = {}
        mock_km.session_to_nanoid = {}
        mock_km.lock = MagicMock()

        # We need to mock the actual methods of kernel_manager because they are called by endpoints
        # But wait, main.kernel_manager IS the instance.

        # Instead of mocking the whole kernel_manager, let's mock only what we need
        # and let the real resolve_session_id run if possible, or mock it too.

        real_km = main.KernelManager()
        with patch('main.kernel_manager', real_km), \
             patch.object(real_km, 'execute_code') as mock_exec, \
             patch.object(real_km, 'list_files') as mock_list, \
             patch.object(real_km, 'get_or_create_container'):

            mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}
            mock_list.return_value = []

            client = TestClient(main.app)

            # 1. First execution creates a mapping
            resp1 = client.post(
                "/exec",
                headers={"X-API-Key": main.API_KEY},
                json={"code": "print(1)", "session_id": "uuid-1"}
            )
            nanoid = resp1.json()["session_id"]
            assert nanoid != "uuid-1"
            assert real_km.session_to_nanoid["uuid-1"] == nanoid
            assert real_km.nanoid_to_session[nanoid] == "uuid-1"
            mock_exec.assert_called_with("uuid-1", "print(1)")

            # 2. Second execution using nanoid should resolve to uuid-1
            resp2 = client.post(
                "/exec",
                headers={"X-API-Key": main.API_KEY},
                json={"code": "print(2)", "session_id": nanoid}
            )
            assert resp2.json()["session_id"] == nanoid
            mock_exec.assert_called_with("uuid-1", "print(2)")

            # 3. Upload using nanoid should resolve to uuid-1
            with patch.object(real_km, 'upload_file') as mock_upload:
                resp3 = client.post(
                    "/upload",
                    headers={"X-API-Key": main.API_KEY},
                    data={"entity_id": nanoid},
                    files={"files": ("file.txt", b"data")}
                )
                assert resp3.status_code == 200
                mock_upload.assert_called_once_with("uuid-1", "file.txt", b"data")
