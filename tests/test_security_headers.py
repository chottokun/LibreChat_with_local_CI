from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_add_security_headers():
    response = client.get("/health")
    assert response.status_code == 200

    # Check for security headers
    assert response.headers["Content-Security-Policy"] == "default-src 'self'; frame-ancestors 'none';"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["Referrer-Policy"] == "no-referrer"
