import pytest
import logging
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException, UploadFile
import main
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    # Clear mappings before each test
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_upload_generic_exception_logging(caplog):
    """
    Triggers a non-HTTPException at L891 to verify it's caught,
    logged with logger.exception("Error processing upload"),
    and returns a 500 status code.
    """
    # Mocking get_or_create_session_mapping to raise a generic Exception
    with patch.object(kernel_manager, 'get_or_create_session_mapping', side_effect=Exception("Database failure")):
        with caplog.at_level(logging.ERROR):
            response = client.post(
                "/upload",
                headers={"X-API-Key": API_KEY},
                data={"session_id": "test-session"},
                files=[("files", ("test.txt", b"content"))]
            )

            assert response.status_code == 500
            assert "Database failure" in response.json()["detail"]
            # Check that "Error processing upload" was logged as an exception/error
            assert "Error processing upload" in caplog.text

def test_upload_http_exception_propagation(caplog):
    """
    Triggers an HTTPException (e.g., 422 for missing files) to verify it's caught at L889
    and re-raised (propagated) correctly, and notably NOT logged as an error by our handler.
    """
    with caplog.at_level(logging.ERROR):
        # Missing files should trigger an HTTPException (422) in our code
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"}
            # No files
        )

        assert response.status_code == 422
        # Verify that our generic "Error processing upload" log is NOT present
        assert "Error processing upload" not in caplog.text

@pytest.mark.anyio
async def test_upload_file_read_exception(caplog):
    """
    Triggers an exception during UploadFile.read() to verify another path to the generic error handler.
    """
    from main import upload_files

    from unittest.mock import AsyncMock
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "corrupt.txt"
    mock_file.read = AsyncMock(side_effect=Exception("Read error"))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as excinfo:
            await upload_files(
                entity_id=None,
                session_id="test",
                files=[mock_file],
                file=None,
                session_id_query=None,
                key=API_KEY
            )

        assert excinfo.value.status_code == 500
        assert "Read error" in excinfo.value.detail
        assert "Error processing upload" in caplog.text
