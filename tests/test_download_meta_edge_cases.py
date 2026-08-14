import os
import mimetypes
from urllib.parse import quote

# Explicitly register mime types to avoid platform-dependent test failures
mimetypes.add_type("text/plain", ".csv")
mimetypes.add_type("text/plain", ".txt")
mimetypes.add_type("application/gzip", ".gz")

# Set environment variable before importing main
os.environ["LIBRECHAT_CODE_API_KEY"] = "test_key"
from main import get_download_meta  # noqa: E402

def test_get_download_meta_empty_string():
    filename = ""
    mime_type, headers = get_download_meta(filename)
    # mimetypes.guess_type("") usually returns (None, None)
    assert mime_type == "application/octet-stream"
    cd = headers["Content-Disposition"]
    assert 'filename="file"' in cd
    assert "filename*=utf-8''" in cd

def test_get_download_meta_long_string():
    base = "a" * 1000
    filename = base + ".txt"
    mime_type, headers = get_download_meta(filename)
    assert mime_type == "text/plain"
    cd = headers["Content-Disposition"]
    assert f'filename="{filename}"' in cd
    assert f"filename*=utf-8''{quote(filename)}" in cd

def test_get_download_meta_whitespace():
    filename = "   "
    mime_type, headers = get_download_meta(filename)
    assert mime_type == "application/octet-stream"
    cd = headers["Content-Disposition"]
    assert 'filename="   "' in cd
    assert f"filename*=utf-8''{quote(filename)}" in cd

def test_get_download_meta_multiple_extensions():
    filename = "archive.tar.gz"
    mime_type, headers = get_download_meta(filename)
    # Depends on system mimetypes, but usually .gz is application/gzip
    # If not found, it falls back to application/octet-stream
    if mime_type == "application/gzip":
        assert "attachment" in headers["Content-Disposition"]

    cd = headers["Content-Disposition"]
    assert 'filename="archive.tar.gz"' in cd

def test_get_download_meta_many_dots():
    filename = "....csv"
    mime_type, headers = get_download_meta(filename)
    assert mime_type == "text/plain"
    assert "inline" in headers["Content-Disposition"]
    cd = headers["Content-Disposition"]
    assert 'filename="....csv"' in cd

def test_get_download_meta_only_stripped_chars():
    # characters that are stripped: \, ", \r, \n
    filename = "\"\n\r\\"
    mime_type, headers = get_download_meta(filename)
    cd = headers["Content-Disposition"]
    # All chars stripped, should fallback to "file"
    assert 'filename="file"' in cd
    assert f"filename*=utf-8''{quote(filename)}" in cd

def test_get_download_meta_url_encoding_needed():
    filename = "file with space.txt"
    mime_type, headers = get_download_meta(filename)
    assert mime_type == "text/plain"
    cd = headers["Content-Disposition"]
    assert 'filename="file with space.txt"' in cd
    assert f"filename*=utf-8''{quote(filename)}" in cd

# ==================== Tough Simulated-UI Integration Tests ====================

def test_upload_japanese_filename():
    """Simulates UI uploading files with Japanese/non-ASCII characters in filename."""
    from fastapi.testclient import TestClient
    import main
    from unittest.mock import patch

    client = TestClient(main.app)
    japanese_filename = "日本語テスト.csv"
    session_id = "test_japanese_session"

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.write_bytes") as mock_write_bytes, \
         patch("main.DOCKER_CLIENT"):

        response = client.post(
            "/upload",
            data={"entity_id": session_id},
            files={"files": (japanese_filename, b"col1,col2\n1,2")},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        res_json = response.json()
        assert res_json["message"] == "success"

        mock_mkdir.assert_called()
        mock_write_bytes.assert_called_once_with(b"col1,col2\n1,2")

def test_upload_double_file_extension():
    """Simulates UI uploading files with double/complex extensions (e.g. archive.tar.gz)."""
    from fastapi.testclient import TestClient
    import main
    from unittest.mock import patch
    from pathlib import Path

    client = TestClient(main.app)
    double_ext_filename = "data_backup.tar.gz"
    session_id = "test_double_ext_session"

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.write_bytes") as mock_write_bytes, \
         patch("main.DOCKER_CLIENT"):

        response = client.post(
            "/upload",
            data={"entity_id": session_id},
            files={"files": (double_ext_filename, b"fake tar gz content")},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        mock_write_bytes.assert_called_once_with(b"fake tar gz content")
        assert Path(double_ext_filename).suffix == ".gz"

def test_sanitize_unicode_japanese_session_id():
    """Simulates UI requests using a session ID with Japanese/Unicode characters, ensuring safe sanitization."""
    from fastapi.testclient import TestClient
    import main
    from unittest.mock import patch

    client = TestClient(main.app)
    unicode_session_id = "セッション_123_!!!"
    sanitized = main.sanitize_id(unicode_session_id)
    assert sanitized == "セッション_123_"

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.write_bytes"), \
         patch("main.DOCKER_CLIENT"):

        response = client.post(
            "/upload",
            data={"entity_id": unicode_session_id},
            files={"files": ("test.txt", b"unicode content")},
            headers={"X-API-Key": main.API_KEY}
        )

        assert response.status_code == 200
        mock_mkdir.assert_called()

