import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    """各テスト実行前に KernelManager のマッピング状態をクリアします。"""
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_download_file_query_success_standard_mode():
    """
    Standard Mode (Docker API 経由) において、
    クエリパラメータを用いた /download エンドポイントからのファイルダウンロードが成功することを検証します。
    """
    session_id = "test_session_std"
    filename = "test_std.txt"
    content = b"hello standard world"
    mtime = 12345.0

    # Advanced Mode (ボリュームマウント) は無効化
    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", return_value=(content, mtime)) as mock_download:

        response = client.get(
            "/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        assert "text/plain" in response.headers["content-type"]
        assert f"filename=\"{filename}\"" in response.headers["content-disposition"]
        mock_download.assert_called_once_with(session_id, filename)

def test_run_download_file_query_success_standard_mode():
    """
    Standard Mode (Docker API 経由) において、
    クエリパラメータを用いた /run/download エンドポイントからのファイルダウンロードが成功することを検証します。
    """
    session_id = "test_session_run"
    filename = "run_std.txt"
    content = b"hello run standard world"
    mtime = 12346.0

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", return_value=(content, mtime)) as mock_download:

        response = client.get(
            "/run/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        mock_download.assert_called_once_with(session_id, filename)

def test_download_session_file_path_params_success_standard_mode():
    """
    Standard Mode において、
    パスパラメータを用いた /download/{session_id}/{filename} からのダウンロードが成功し、
    拡張子に応じた Content-Type や Content-Disposition が正しく設定されることを検証します。
    """
    session_id = "path_session_std"
    filename = "photo.png"
    content = b"fake-png-binary-data"
    mtime = 22222.0

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", return_value=(content, mtime)) as mock_download:

        response = client.get(
            f"/download/{session_id}/{filename}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        assert "image/png" in response.headers["content-type"]
        assert "inline" in response.headers["content-disposition"]
        mock_download.assert_called_once_with(session_id, filename)

def test_download_session_file_advanced_mode_success(tmp_path):
    """
    Advanced Mode (ボリュームマウント有効) において、
    ホスト側ディレクトリに設置された物理ファイルが正常にロードされダウンロードできることを実テストで検証します。
    """
    session_id = "adv_session_id"
    filename = "adv_file.txt"
    content = b"advanced mode physical file content"

    # テスト用の一時共有ボリュームの構造を準備
    internal_dir = tmp_path / "shared_sessions"
    session_dir = internal_dir / session_id
    session_dir.mkdir(parents=True)
    file_path = session_dir / filename
    file_path.write_bytes(content)

    with patch("main.RCE_DATA_DIR_HOST", "some/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", str(internal_dir)):

        response = client.get(
            "/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content

def test_download_session_file_nanoid_resolution():
    """
    LibreChatで使用される Nanoid 形式の ID が渡された場合に、
    登録された本物の UUID セッションID および本物のファイル名に適切に解決されて
    ダウンロードが行われることを検証します。
    """
    nanoid_session_id = "nano-sess-123"
    real_session_id = "real-uuid-session-abc"
    nanoid_file_id = "file-id-xyz"
    real_filename = "actual_document.csv"
    content = b"col1,col2\nval1,val2"
    mtime = 99999.0

    # KernelManager のマッピング情報を設定
    with kernel_manager.lock:
        kernel_manager.nanoid_to_session[nanoid_session_id] = real_session_id
        kernel_manager.file_id_map[nanoid_session_id] = {nanoid_file_id: real_filename}

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", return_value=(content, mtime)) as mock_download:

        response = client.get(
            f"/download/{nanoid_session_id}/{nanoid_file_id}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == content
        # download_file は解決された本物の ID で呼ばれる必要がある
        mock_download.assert_called_once_with(real_session_id, real_filename)
        assert "text/plain" in response.headers["content-type"]

def test_download_file_query_unauthorized():
    """無効な API キーが与えられた場合に 401 Unauthorized エラーを返すことを検証します。"""
    response = client.get(
        "/download",
        params={"session_id": "test", "filename": "test.txt"},
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 401

def test_download_file_query_missing_params():
    """必須のクエリパラメータが不足している場合に 422 Unprocessable Entity エラーを返すことを検証します。"""
    # filename 不足
    response = client.get(
        "/download",
        params={"session_id": "test_session"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

    # session_id 不足
    response = client.get(
        "/download",
        params={"filename": "test.txt"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

def test_download_file_query_not_found():
    """ファイルが存在しない場合に 404 Not Found エラーを返すことを検証します。"""
    from fastapi import HTTPException

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, "download_file", side_effect=HTTPException(status_code=404, detail="File not found")):

        response = client.get(
            "/download",
            params={"session_id": "s", "filename": "missing.txt"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "File not found"


def test_download_session_file_alternate_routes():
    """
    パスパラメータを用いるすべてのダウンロードルート（/api/files/code/download, /download, /run/download）が
    正しくマッピングされ、同様に動作することを検証します。
    """
    routes = [
        "/api/files/code/download/s/f.txt",
        "/download/s/f.txt",
        "/run/download/s/f.txt"
    ]

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:
        mock_download.return_value = (b"alternate route content", 123.0)

        for route in routes:
            response = client.get(route, headers={"X-API-Key": API_KEY})
            assert response.status_code == 200
            assert response.content == b"alternate route content"


def test_download_binary_mime_type():
    """
    バイナリファイル（.binなど）がダウンロードされた場合、
    MIMEタイプが application/octet-stream となり、Content-Disposition が attachment になることを検証します。
    """
    session_id = "binary_session"
    filename = "data.bin"
    content = b"\x00\x01\x02\x03"

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:
        mock_download.return_value = (content, 12345.0)

        response = client.get(
            f"/download/{session_id}/{filename}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment")


def test_download_non_ascii_filename():
    """
    日本語などの非ASCII文字ファイル名（例: テスト.txt）をダウンロードした際に、
    Content-Disposition ヘッダーにおいて正しく RFC 5987 に従ってパーセントエンコーディングされ、
    ASCIIへの安全なフォールバック（filename=".txt"）が行われることを検証します。
    """
    from urllib.parse import quote
    session_id = "non_ascii_session"
    filename = "テスト.txt"
    content = b"japanese file content"

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:
        mock_download.return_value = (content, 12345.0)

        response = client.get(
            f"/download/{session_id}/{filename}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        cd = response.headers["Content-Disposition"]
        
        # ASCII文字のみのフォールバックの確認
        assert 'filename=".txt"' in cd
        
        # UTF-8 URLエンコードの確認 (テスト.txt -> %E3%83%86%E3%82%B9%E3%83%88.txt)
        expected_encoded = quote(filename)
        assert f"filename*=utf-8''{expected_encoded}" in cd

