import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import os
import main
from main import app, API_KEY

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    """Reset the kernel manager state before each test."""
    main.kernel_manager.nanoid_to_session = {}
    main.kernel_manager.session_to_nanoid = {}
    main.kernel_manager.file_id_map = {}
    yield

def test_download_file_unauthorized():
    response = client.get("/download/session/file", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401

@patch("main.kernel_manager.download_file")
@patch("main.RCE_DATA_DIR_HOST", None)
@patch("tempfile.NamedTemporaryFile")
@patch("main.FileResponse")
@patch("os.remove")
def test_download_session_file_standard_mode(mock_remove, mock_fileresponse, mock_tempfile, mock_download):
    # Setup
    session_id = "test_session"
    filename = "test.txt"
    content = b"hello world"
    mock_download.return_value = (content, 123456789)

    mock_temp = MagicMock()
    mock_temp.name = "/tmp/fakefile"
    mock_tempfile.return_value.__enter__.return_value = mock_temp

    mock_fileresponse.return_value = MagicMock(status_code=200)

    # Execute
    response = client.get(f"/download/{session_id}/{filename}", headers={"X-API-Key": API_KEY})

    # Assert
    assert response.status_code == 200
    mock_download.assert_called_once_with(session_id, filename)
    mock_fileresponse.assert_called_once()
    args, kwargs = mock_fileresponse.call_args
    assert kwargs["path"] == "/tmp/fakefile"
    assert kwargs["media_type"] == "text/plain"
    assert "attachment" in kwargs["headers"]["Content-Disposition"]

@patch("main.RCE_DATA_DIR_HOST", "/host/path")
@patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path")
@patch("os.path.exists", return_value=True)
@patch("main.FileResponse")
def test_download_session_file_advanced_mode(mock_fileresponse, mock_exists):
    # Setup
    session_id = "test_session"
    filename = "test.txt"

    mock_fileresponse.return_value = MagicMock(status_code=200)

    # Execute
    response = client.get(f"/download/{session_id}/{filename}", headers={"X-API-Key": API_KEY})

    # Assert
    assert response.status_code == 200
    mock_fileresponse.assert_called_once()
    args, kwargs = mock_fileresponse.call_args
    assert kwargs["path"] == f"/internal/path/{session_id}/{filename}"
    assert kwargs["media_type"] == "text/plain"

def test_download_session_file_nanoid_resolution():
    # Setup
    nanoid_session = "nanoid_s"
    real_session = "real_s"
    nanoid_file = "nanoid_f"
    real_file = "real.png"

    main.kernel_manager.nanoid_to_session[nanoid_session] = real_session
    main.kernel_manager.file_id_map[nanoid_session] = {nanoid_file: real_file}

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=True), \
         patch("main.FileResponse") as mock_fileresponse:

        mock_fileresponse.return_value = MagicMock(status_code=200)

        # Execute
        response = client.get(f"/api/files/code/download/{nanoid_session}/{nanoid_file}", headers={"X-API-Key": API_KEY})

        # Assert
        assert response.status_code == 200
        mock_fileresponse.assert_called_once()
        args, kwargs = mock_fileresponse.call_args
        # Should resolve to real IDs
        assert kwargs["path"] == f"/internal/path/{real_session}/{real_file}"
        assert kwargs["media_type"] == "image/png"
        assert "inline" in kwargs["headers"]["Content-Disposition"]

@patch("main.kernel_manager.download_file")
@patch("main.RCE_DATA_DIR_HOST", None)
@patch("tempfile.NamedTemporaryFile")
@patch("main.FileResponse")
@patch("os.remove")
def test_download_file_query_params(mock_remove, mock_fileresponse, mock_tempfile, mock_download):
    # Setup
    session_id = "test_session"
    filename = "test.txt"
    content = b"hello query"
    mock_download.return_value = (content, 123456789)

    mock_temp = MagicMock()
    mock_temp.name = "/tmp/fakefile_query"
    mock_tempfile.return_value.__enter__.return_value = mock_temp

    mock_fileresponse.return_value = MagicMock(status_code=200)

    # Execute
    response = client.get(f"/download?session_id={session_id}&filename={filename}", headers={"X-API-Key": API_KEY})

    # Assert
    assert response.status_code == 200
    mock_download.assert_called_once_with(session_id, filename)
    mock_fileresponse.assert_called_once()

@patch("main.RCE_DATA_DIR_HOST", "/host/path")
@patch("os.path.exists", return_value=False)
def test_download_session_file_not_found_advanced(mock_exists):
    response = client.get("/download/s/f", headers={"X-API-Key": API_KEY})
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"

@patch("main.kernel_manager.download_file")
@patch("main.RCE_DATA_DIR_HOST", None)
def test_download_session_file_not_found_standard(mock_download):
    from fastapi import HTTPException
    mock_download.side_effect = HTTPException(status_code=404, detail="File not found")

    response = client.get("/download/s/f", headers={"X-API-Key": API_KEY})
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"

def test_download_disposition_for_pdf():
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=True), \
         patch("main.FileResponse") as mock_fileresponse:

        mock_fileresponse.return_value = MagicMock(status_code=200)

        response = client.get("/download/s/test.pdf", headers={"X-API-Key": API_KEY})

        assert response.status_code == 200
        args, kwargs = mock_fileresponse.call_args
        assert "inline" in kwargs["headers"]["Content-Disposition"]
        assert kwargs["media_type"] == "application/pdf"

def test_download_japanese_filename_headers():
    filename = "テスト.txt"
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=True), \
         patch("main.FileResponse") as mock_fileresponse:

        mock_fileresponse.return_value = MagicMock(status_code=200)

        response = client.get(f"/download/s/{filename}", headers={"X-API-Key": API_KEY})

        assert response.status_code == 200
        args, kwargs = mock_fileresponse.call_args
        disposition = kwargs["headers"]["Content-Disposition"]
        assert "filename=\".txt\"" in disposition
        assert "filename*=utf-8''%E3%83%86%E3%82%B9%E3%83%88.txt" in disposition
