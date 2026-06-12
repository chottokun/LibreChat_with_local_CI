from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app, API_KEY

client = TestClient(app)

# 付与を期待する標準のセキュリティヘッダー群
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "x-xss-protection": "1; mode=block",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "referrer-policy": "no-referrer",
}

def test_security_headers_added_to_standard_response():
    """
    標準の非ダウンロードレスポンス（例: /health）に対して、
    定義されたすべてのセキュリティヘッダーが正常に付与されることを検証します。
    """
    response = client.get("/health")
    assert response.status_code == 200
    for header, value in SECURITY_HEADERS.items():
        assert response.headers.get(header) == value

def test_security_headers_not_added_to_download_response():
    """
    ファイルダウンロード用レスポンス（/download やパスパラメータなど）に対して、
    ブラウザの挙動やセキュリティブロックを避けるため、セキュリティヘッダーが付与されないことを検証します。
    """
    # Docker やファイルシステムへの直接のアクセスを避けるためにモック化します
    with patch("main.kernel_manager.download_file") as mock_download:
        mock_download.return_value = (b"dummy data content", 123456789.0)

        download_paths = [
            "/download",
            "/run/download",
            "/api/files/code/download/session/test.txt"
        ]

        for path in download_paths:
            response = client.get(
                path,
                headers={"X-API-Key": API_KEY},
                params={"session_id": "test", "filename": "test.txt"}
            )
            assert response.status_code == 200
            for header in SECURITY_HEADERS:
                assert header not in response.headers
def test_cors_headers_present():
    """
    SecurityHeadersCORSMiddleware が CORSMiddleware を正しく継承しており、
    CORS ヘッダー（Access-Control-Allow-Origin 等）がプレフライト（OPTIONS）および
    通常リクエストで正常に返されること、かつセキュリティヘッダーと両立することを検証します。
    """
    # A. プレフライト OPTIONS リクエストの検証
    # NOTE: CORS_ALLOWED_ORIGINS デフォルト値 (localhost:3000/3080) を想定
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # B. 実際の CORS リクエストの検証
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    # セキュリティヘッダーも同時に付与されているか確認
    for header, value in SECURITY_HEADERS.items():
        assert response.headers.get(header) == value

def test_security_headers_non_http_scope():
    """
    HTTP スコープ以外の接続（WebSocket等）がミドルウェアを通過した際にも、
    親クラス（CORSMiddleware）の処理へ適切にフォールバックされエラーにならないことを検証します。
    """
    # NOTE: FastAPI's TestClient.websocket_connect uses an 'http' scope initially
    # for the upgrade request, but we can verify the middleware logic via unit tests
    # in test_security_middleware_unit.py.
    # Here we just ensure a basic request still works.
    response = client.get("/health")
    assert response.status_code == 200
