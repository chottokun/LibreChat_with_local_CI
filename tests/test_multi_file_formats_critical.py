import os
import pytest
import mimetypes
from urllib.parse import quote
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from fastapi.testclient import TestClient

# Register custom MIME types for test isolation
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("text/plain", ".csv")
mimetypes.add_type("text/plain", ".txt")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")
mimetypes.add_type("application/zip", ".zip")

# Set test key before importing main
os.environ["LIBRECHAT_CODE_API_KEY"] = "test-secret-key"
import main  # noqa: E402
from main import app, get_download_meta  # noqa: E402


# ==============================================================================
# 1. Multi-Format MIME and Content-Disposition Matrix Tests (PDF, Media, Docs)
# ==============================================================================

@pytest.mark.parametrize("filename,expected_disposition", [
    # PDF Documents (Must be inline for browser/LibreChat viewing)
    ("report.pdf", "inline"),
    ("ANALYSIS_SUMMARY.PDF", "inline"),
    ("日本語ドキュメント.pdf", "inline"),
    
    # Images (Must be inline for rendering charts and plots)
    ("chart.png", "inline"),
    ("PHOTO.JPEG", "inline"),
    ("photo.jpg", "inline"),
    ("diagram.svg", "inline"),
    ("graphic.webp", "inline"),
    
    # Text & Data (CSV is forced to text/plain & inline to avoid Chrome blocking)
    ("data.csv", "inline"),
    ("FINANCIAL_DATA.CSV", "inline"),
    ("README.md", "inline"),
    ("config.json", "attachment"),
    ("log.txt", "inline"),
    
    # Office & Binary Archives (Must be attachment)
    ("spreadsheet.xlsx", "attachment"),
    ("dataset.parquet", "attachment"),
    ("backup.zip", "attachment"),
    ("archive.tar.gz", "attachment"),
    ("binary.bin", "attachment"),
])
def test_get_download_meta_format_matrix(filename, expected_disposition):
    """
    Validates MIME type detection and Content-Disposition header construction
    for PDF, image, audio/video, office, and binary data formats.
    """
    mime_type, headers = get_download_meta(filename)
    
    assert mime_type is not None
    assert expected_disposition in headers["Content-Disposition"]
    
    # RFC 5987 UTF-8 encoded filename must always be present
    encoded_name = quote(filename)
    assert f"filename*=utf-8''{encoded_name}" in headers["Content-Disposition"]


# ==============================================================================
# 2. PDF End-to-End Upload & Download Lifecycle (Binary Preservation)
# ==============================================================================

def test_pdf_upload_and_download_flow():
    """
    Tests complete lifecycle of a PDF file:
    1. Upload binary PDF bytes to sandbox.
    2. Verify binary integrity (magic bytes '%PDF-1.7...').
    3. Download PDF and ensure inline disposition and proper MIME headers.
    """
    client = TestClient(app)
    session_id = "pdf_test_session"
    pdf_filename = "四半期業績報告書.pdf"
    
    # Realistic PDF byte header and content
    pdf_content = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
    
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.write_bytes") as mock_write_bytes, \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve") as mock_resolve, \
         patch("os.stat") as mock_os_stat, \
         patch("anyio.open_file") as mock_open_file, \
         patch("main.DOCKER_CLIENT"):

        # 1. Upload PDF via /upload
        upload_resp = client.post(
            "/upload",
            data={"entity_id": session_id},
            files={"files": (pdf_filename, pdf_content, "application/pdf")},
            headers={"X-API-Key": "test-secret-key"}
        )
        assert upload_resp.status_code == 200
        upload_json = upload_resp.json()
        assert upload_json["message"] == "success"
        
        # Verify directory creation and exact binary write
        mock_mkdir.assert_called()
        mock_write_bytes.assert_called_once_with(pdf_content)

        # 2. Setup mock for Download
        mock_stat_result = MagicMock()
        mock_stat_result.st_size = len(pdf_content)
        mock_stat_result.st_mtime = 1700000000.0
        mock_stat_result.st_mode = 33188
        mock_os_stat.return_value = mock_stat_result

        mock_file = MagicMock()
        mock_file.__aenter__.return_value = MagicMock(read=AsyncMock(return_value=pdf_content))
        mock_open_file.return_value = mock_file
        mock_resolve.side_effect = lambda *args, **kwargs: Path(f"/internal/path/{session_id}/{pdf_filename}")

        # 3. Download PDF via /download
        with patch.object(main.kernel_manager, "resolve_download_ids", return_value=(session_id, pdf_filename)):
            download_resp = client.get(
                f"/download/{session_id}/{pdf_filename}",
                headers={"X-API-Key": "test-secret-key"}
            )
            assert download_resp.status_code == 200
            assert download_resp.headers["content-type"].startswith("application/pdf")
            assert "inline" in download_resp.headers["content-disposition"]
            assert download_resp.content == pdf_content


# ==============================================================================
# 3. Adversarial / Critical Security & Edge-Case Tests
# ==============================================================================

def test_adversarial_double_extension_disguise():
    """
    Test defense against double extension exploits like 'report.pdf.exe' or 'exploit.php.png'.
    The MIME type and disposition must follow the FINAL extension (.exe or .png).
    """
    # 1. PDF disguised executable (must be treated as executable binary / attachment)
    _, headers_exe = get_download_meta("malicious_report.pdf.exe")
    assert "attachment" in headers_exe["Content-Disposition"]

    # 2. PHP disguised as image
    mime_png, headers_png = get_download_meta("payload.php.png")
    assert mime_png == "image/png"
    assert "inline" in headers_png["Content-Disposition"]


def test_adversarial_header_injection():
    """
    Test that CRLF injections and quote injection in filenames are neutralized
    in Content-Disposition headers (preventing HTTP response splitting).
    """
    malicious_filename = 'report\r\nSet-Cookie: admin=true\n"injection.pdf'
    _, headers = get_download_meta(malicious_filename)
    cd = headers["Content-Disposition"]
    
    # Raw CR and LF must not be present in the ASCII fallback parameter
    assert "\r" not in cd
    assert "\n" not in cd
    # Unescaped double quotes inside the quotes must be stripped
    assert 'reportSet-Cookie: admin=trueinjection.pdf' in cd


def test_adversarial_path_traversal_variations():
    """
    Tests various adversarial path traversal patterns against KernelManager.download_file.
    All must be safely rejected with 400 Bad Request or 403 Forbidden.
    """
    km = main.kernel_manager
    session_id = "test_session_id"

    adversarial_paths = [
        "../../etc/passwd",
        "/etc/shadow",
        "nested/../../../secret.txt",
        "....//....//etc/passwd",
        "test/../../..",
        "/root/.ssh/id_rsa",
    ]

    for bad_path in adversarial_paths:
        with pytest.raises((main.HTTPException, FileNotFoundError)) as exc_info:
            km.download_file(session_id, bad_path)
        if isinstance(exc_info.value, main.HTTPException):
            assert exc_info.value.status_code in (400, 403, 404)


def test_empty_file_upload_rejection():
    """
    Tests that uploading 0-byte (empty) files is strictly rejected with 400 Bad Request.
    """
    client = TestClient(app)
    response = client.post(
        "/upload",
        data={"entity_id": "session_empty_test"},
        files={"files": ("empty.pdf", b"", "application/pdf")},
        headers={"X-API-Key": "test-secret-key"}
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_unicode_special_characters_in_filename():
    """
    Validates handling of Unicode emojis, symbols, and CJK characters in file metadata.
    """
    unicode_filename = "📊_売上_Q1_📈_v1.0 (最新版).pdf"
    mime, headers = get_download_meta(unicode_filename)
    
    assert mime == "application/pdf"
    cd = headers["Content-Disposition"]
    assert "inline" in cd
    assert "filename*=utf-8''" in cd
    # Check that URL encoding accurately encodes multibyte CJK and emoji
    assert quote(unicode_filename) in cd
