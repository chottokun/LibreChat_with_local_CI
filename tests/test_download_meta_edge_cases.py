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
