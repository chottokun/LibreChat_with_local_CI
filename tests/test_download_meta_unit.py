import pytest
import os
import mimetypes
from urllib.parse import quote

# Explicitly register mime types to avoid platform-dependent test failures (e.g. .py returning different types on Windows/macOS)
mimetypes.add_type("text/x-python", ".py")
mimetypes.add_type("text/plain", ".txt")
mimetypes.add_type("text/plain", ".csv")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("application/zip", ".zip")

# Set environment variable before importing main
os.environ["LIBRECHAT_CODE_API_KEY"] = "test_key"
from main import get_download_meta

@pytest.mark.parametrize("filename, expected_mime, expected_disposition", [
    ("test.csv", "text/plain", "inline"),
    ("image.png", "image/png", "inline"),
    ("photo.jpg", "image/jpeg", "inline"),
    ("doc.pdf", "application/pdf", "inline"),
    ("readme.txt", "text/plain", "inline"),
    ("script.py", "text/x-python", "inline"),
    ("data.bin", "application/octet-stream", "attachment"),
    ("archive.zip", "application/zip", "attachment"),
])
def test_get_download_meta_mime_and_disposition(filename, expected_mime, expected_disposition):
    mime_type, headers = get_download_meta(filename)
    assert mime_type == expected_mime
    assert f"{expected_disposition};" in headers["Content-Disposition"]

def test_get_download_meta_csv_special_handling():
    # Even if mimetypes would normally guess something else, CSV should be text/plain
    mime_type, headers = get_download_meta("DATA.CSV")
    assert mime_type == "text/plain"
    assert "inline" in headers["Content-Disposition"]

def test_get_download_meta_non_ascii_filename():
    filename = "テスト.txt"
    mime_type, headers = get_download_meta(filename)

    cd = headers["Content-Disposition"]
    # Check ASCII fallback: "テスト.txt" -> ".txt"
    assert 'filename=".txt"' in cd
    # Check RFC 5987 encoding
    expected_encoded = quote(filename)
    assert f"filename*=utf-8''{expected_encoded}" in cd

def test_get_download_meta_pure_non_ascii_filename():
    filename = "こんにちは"
    mime_type, headers = get_download_meta(filename)

    cd = headers["Content-Disposition"]
    # Check ASCII fallback: nothing left, should be "file"
    assert 'filename="file"' in cd
    # Check RFC 5987 encoding
    expected_encoded = quote(filename)
    assert f"filename*=utf-8''{expected_encoded}" in cd

def test_get_download_meta_sanitization():
    filename = 'file"with"quotes\nand\rnewlines\\and\t-tabs.txt'
    # ASCII fallback should remove ", \, \n, \r.
    mime_type, headers = get_download_meta(filename)
    cd = headers["Content-Disposition"]

    # expected: filewithquotesandnewlinesand-tabs.txt
    assert 'filename="filewithquotesandnewlinesand\t-tabs.txt"' in cd

    expected_encoded = quote(filename)
    assert f"filename*=utf-8''{expected_encoded}" in cd

def test_get_download_meta_unknown_extension():
    filename = "unknown.voodoo"
    mime_type, headers = get_download_meta(filename)

    assert mime_type == "application/octet-stream"
    assert "attachment" in headers["Content-Disposition"]
