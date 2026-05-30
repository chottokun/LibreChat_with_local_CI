import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app, API_KEY

client = TestClient(app)

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "x-xss-protection": "1; mode=block",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "referrer-policy": "no-referrer",
}

def test_security_headers_added_to_standard_response():
    """Verify that security headers are added to a standard non-download response."""
    response = client.get("/health")
    assert response.status_code == 200
    for header, value in SECURITY_HEADERS.items():
        assert response.headers.get(header) == value

def test_security_headers_not_added_to_download_response():
    """Verify that security headers are NOT added to download responses."""
    # Mocking KernelManager.download_file to avoid actual file system/docker calls
    with patch("main.kernel_manager.download_file") as mock_download:
        mock_download.return_value = (b"data", 123456789.0)

        # Test various download prefixes
        download_paths = [
            "/download",
            "/run/download",
            "/api/files/code/download/session/test.txt"
        ]

        for path in download_paths:
            response = client.get(path, headers={"X-API-Key": API_KEY}, params={"session_id": "test", "filename": "test.txt"})
            assert response.status_code == 200
            for header in SECURITY_HEADERS:
                assert header not in response.headers

def test_cors_headers_present():
    """Verify that CORS headers are still present as SecurityHeadersCORSMiddleware inherits from CORSMiddleware."""
    # Preflight request
    response = client.options(
        "/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://example.com"

    # Actual request
    response = client.get("/health", headers={"Origin": "http://example.com"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://example.com"
    # Security headers should also be present here
    for header, value in SECURITY_HEADERS.items():
        assert response.headers.get(header) == value

def test_security_headers_non_http_scope():
    """
    While we can't easily test non-HTTP scope with TestClient,
    the code handles it by calling super().__call__.
    This test ensures we didn't break basic functionality.
    """
    response = client.get("/health")
    assert response.status_code == 200
