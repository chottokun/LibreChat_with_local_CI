import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import os
import tempfile
import shutil
import main

# Mock docker.from_env before importing main app if not already done in the module
# However, we can also patch main.kernel_manager later.

@pytest.fixture
def client():
    # Reset kernel manager state to avoid interference from other tests
    main.kernel_manager.active_kernels = {}
    main.kernel_manager.nanoid_to_session = {}
    main.kernel_manager.session_to_nanoid = {}
    main.kernel_manager.file_id_map = {}

    with patch('main.DOCKER_CLIENT'):
        yield TestClient(main.app)

@pytest.fixture
def temp_data_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

def test_download_file_query_docker_api(client):
    """
    Test download via the Docker API path (RCE_DATA_DIR_INTERNAL is None).
    """
    session_id = "test-session"
    filename = "test.txt"
    content = b"hello docker api"

    with patch('main.RCE_DATA_DIR_INTERNAL', None), \
         patch('main.kernel_manager.download_file') as mock_download:

        mock_download.return_value = (content, 123456789)

        response = client.get(
            "/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert f'filename="{filename}"' in response.headers["content-disposition"]
        mock_download.assert_called_once_with(session_id, filename)

def test_download_file_path_volume_mount(client, temp_data_dir):
    """
    Test download via the Volume Mount path (RCE_DATA_DIR_INTERNAL is set).
    """
    session_id = "test-session-vol"
    filename = "test_vol.txt"
    content = b"hello volume mount"

    # Setup the file on the "host" (which is temp_data_dir in this test)
    session_dir = os.path.join(temp_data_dir, session_id)
    os.makedirs(session_dir)
    filepath = os.path.join(session_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    with patch('main.RCE_DATA_DIR_HOST', temp_data_dir), \
         patch('main.RCE_DATA_DIR_INTERNAL', temp_data_dir):
        response = client.get(
            f"/download/{session_id}/{filename}",
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]

def test_download_librechat_id_resolution(client):
    """
    Test that nanoid session and file IDs are correctly resolved.
    """
    nanoid_session = "nanoid-session-123"
    real_session = "real-uuid-456"
    nanoid_file = "nanoid-file-789"
    real_filename = "actual_report.pdf"
    content = b"%PDF-1.4 dummy content"

    # Setup mappings in kernel_manager
    with patch.object(main.kernel_manager, 'nanoid_to_session', {nanoid_session: real_session}), \
         patch.object(main.kernel_manager, 'file_id_map', {nanoid_session: {nanoid_file: real_filename}}), \
         patch('main.RCE_DATA_DIR_INTERNAL', None), \
         patch('main.kernel_manager.download_file') as mock_download:

        mock_download.return_value = (content, 123456789)

        response = client.get(
            f"/download/{nanoid_session}/{nanoid_file}",
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        assert response.headers["content-type"] == "application/pdf"
        assert "inline" in response.headers["content-disposition"]
        assert f'filename="{real_filename}"' in response.headers["content-disposition"]
        # Ensure it was called with REAL IDs
        mock_download.assert_called_once_with(real_session, real_filename)

def test_download_mime_types(client):
    """
    Test various MIME types and their corresponding Content-Disposition.
    """
    scenarios = [
        ("image.png", b"fake-png", "image/png", "inline"),
        ("document.pdf", b"%PDF-", "application/pdf", "inline"),
        ("data.csv", b"a,b,c", "text/csv; charset=utf-8", "attachment"),
        ("script.py", b"print(1)", "text/x-python; charset=utf-8", "attachment"),
    ]

    for filename, content, expected_mime, expected_disposition in scenarios:
        with patch('main.RCE_DATA_DIR_INTERNAL', None), \
             patch('main.kernel_manager.download_file') as mock_download:

            mock_download.return_value = (content, 123456789)

            response = client.get(
                "/download",
                params={"session_id": "test", "filename": filename},
                headers={"X-API-Key": main.API_KEY}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == expected_mime
            assert expected_disposition in response.headers["content-disposition"]

def test_download_unauthorized(client):
    response = client.get(
        "/download",
        params={"session_id": "test", "filename": "test.txt"},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401

def test_download_not_found_docker_api(client):
    with patch('main.RCE_DATA_DIR_INTERNAL', None), \
         patch('main.kernel_manager.download_file') as mock_download:

        from fastapi import HTTPException
        mock_download.side_effect = HTTPException(status_code=404, detail="File not found")

        response = client.get(
            "/download",
            params={"session_id": "test", "filename": "missing.txt"},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 404

def test_download_not_found_volume_mount(client, temp_data_dir):
    with patch('main.RCE_DATA_DIR_HOST', temp_data_dir), \
         patch('main.RCE_DATA_DIR_INTERNAL', temp_data_dir):
        response = client.get(
            "/download/test-session/missing.txt",
            headers={"X-API-Key": main.API_KEY}
        )
        assert response.status_code == 404
