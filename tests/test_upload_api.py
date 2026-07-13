import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import main
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    # テスト間の分離を保証するため、グローバル状態およびマッピングをクリア
    main.LAST_UPLOADED_SESSION_ID = None
    main.LAST_UPLOAD_TIME = 0
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_upload_success_entity_id():
    with patch.object(kernel_manager, 'upload_files_batch') as mock_upload:
        # Pass multiple files with the same key "files"
        files = [
            ("files", ("test1.txt", b"content1")),
            ("files", ("test2.txt", b"content2"))
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": "test-session"},
            files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "success"
        assert len(data["files"]) == 2
        assert data["files"][0]["filename"] == "test1.txt"
        assert data["files"][1]["filename"] == "test2.txt"

        # Verify kernel_manager was called
        assert mock_upload.call_count == 1

        # Check if session mapping was created
        nanoid_session = data["session_id"]
        with kernel_manager.lock:
            assert nanoid_session in kernel_manager.nanoid_to_session

def test_upload_success_session_id_field():
    with patch.object(kernel_manager, 'upload_files_batch') as mock_upload:
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "session-123"},
            files=[("file", ("file1.txt", b"data1"))]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-123"

        assert len(data["files"]) == 1
        assert data["filename"] == "file1.txt"
        mock_upload.assert_called_once()

def test_upload_success_query_param():
    with patch.object(kernel_manager, 'upload_files_batch'):
        response = client.post(
            "/upload?session_id=query-session",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("q.txt", b"q-data"))]
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == "query-session"

def test_upload_no_session_id_generates_one():
    with patch.object(kernel_manager, 'upload_files_batch'):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("auto.txt", b"auto-content"))]
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 21 # Nanoid size

def test_upload_no_files_fails():
    response = client.post(
        "/upload",
        headers={"X-API-Key": API_KEY},
        data={"entity_id": "some-id"}
    )
    assert response.status_code == 422
    assert "No files provided" in response.json()["detail"]

def test_upload_unauthorized():
    with patch("main.DISABLE_AUTH", False):
        response = client.post(
            "/upload",
            headers={"X-API-Key": "wrong-key"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 401

def test_upload_priority_files_over_file():
    # Tests that 'files' takes priority over 'file' if both are present
    with patch.object(kernel_manager, 'upload_files_batch') as mock_upload:
        files = [
            ("files", ("f1.txt", b"c1")),
            ("file", ("f2.txt", b"c2"))
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": "mixed-id"},
            files=files
        )

        assert response.status_code == 200
        # According to current code: files = form.getlist("files") or form.getlist("file")
        # So only f1.txt should be uploaded.
        assert len(response.json()["files"]) == 1
        assert response.json()["files"][0]["filename"] == "f1.txt"
        assert mock_upload.call_count == 1


def test_upload_duplicate_files_reuses_id():
    """
    同一セッション内で同じファイル（名前およびコンテンツ）を複数回アップロードした際に、
    新しいファイルIDを発行せず、既存のファイルIDが再利用されることを検証します。
    """
    with patch.object(kernel_manager, 'upload_files_batch'):
        session_id = "test-session-dup"
        filename = "duplicate.txt"
        content = b"some shared file content"

        # 1回目のアップロード
        response1 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": session_id},
            files=[("files", (filename, content))]
        )
        assert response1.status_code == 200
        file_id1 = response1.json()["files"][0]["fileId"]

        # 2回目のアップロード
        response2 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": session_id},
            files=[("files", (filename, content))]
        )
        assert response2.status_code == 200
        file_id2 = response2.json()["files"][0]["fileId"]

        assert file_id1 == file_id2


def test_upload_invalid_filename_empty():
    """
    ファイル名が空、またはスラッシュのみのディレクトリ構造のように basename が空になる場合に、
    400 Bad Request ("Invalid filename") を返して拒絶されることを検証します。
    """
    with patch.object(kernel_manager, 'upload_files_batch'):
        # スラッシュのみでファイル名が空になるケース
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session-empty"},
            files=[("files", ("/", b"content"))]
        )
        assert response.status_code == 400
        assert "Invalid filename" in response.json()["detail"]


@pytest.mark.anyio
async def test_upload_invalid_filename_none_unit():
    """
    UploadFile.filename が None の場合に 400 Bad Request を返すことを、
    HTTPルーティングを介さずに upload_files ハンドラ関数を直接呼び出して検証します。
    """
    from main import upload_files, HTTPException
    from fastapi import UploadFile
    from unittest.mock import MagicMock

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = None

    with pytest.raises(HTTPException) as excinfo:
        await upload_files(
            entity_id=None,
            session_id="test",
            files=[mock_file],
            file=None,
            session_id_query=None,
            key=API_KEY
        )

    assert excinfo.value.status_code == 400
    assert "Invalid filename" in excinfo.value.detail


def test_upload_updates_global_state():
    """
    アップロードが成功した際に、最後のセッションIDとアップロード日時を記録する
    グローバル状態（LAST_UPLOADED_SESSION_ID / LAST_UPLOAD_TIME）が正しく更新されることを検証します。
    """
    import time
    with patch.object(kernel_manager, 'upload_files_batch'):
        session_id = "global-test-session"

        # アップロードの実行
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": session_id},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 200

        # グローバル変数の状態変化を検証
        assert main.LAST_UPLOADED_SESSION_ID == session_id
        assert main.LAST_UPLOAD_TIME > 0
        assert time.time() - main.LAST_UPLOAD_TIME < 5


def test_upload_generic_exception_handling():
    """
    アップロード処理中に想定外のエラー（例外など）が発生した場合に、
    適切に捕捉され 500 Internal Server Error を返すことを検証します。
    """
    with patch.object(kernel_manager, 'upload_files_batch', side_effect=Exception("Unexpected error during save")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "error-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 500
        assert "Unexpected error" in response.json()["detail"]


def test_upload_kernel_manager_mock_fallback():
    """
    KernelManager がモックオブジェクトなど簡易化されている場合の
    アップロードAPIのフォールバック分岐が正常に機能することを検証します。
    """
    mock_km = MagicMock(spec=main.KernelManager)
    mock_km.resolve_session_id.return_value = "internal-uuid-mock"
    mock_km.lock = MagicMock()
    mock_km.file_id_map = {}

    with patch("main.kernel_manager", mock_km):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "mock-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 200
        mock_km.resolve_session_id.assert_called_once()
        mock_km.get_or_create_session_mapping.assert_not_called()


def test_upload_sanitizes_path():
    """
    パスセグメント付きファイル名（例: path/to/secret.txt）でアップロードされた際、
    パスが除去され、ファイル名の basename（secret.txt）のみで処理されることを検証します。
    """
    with patch.object(kernel_manager, 'upload_files_batch') as mock_upload:
        files = [("files", ("path/to/secret.txt", b"content"))]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "sanitize-session"},
            files=files
        )

        assert response.status_code == 200
        mock_upload.assert_called_once()
        # パスが除去され、basename である secret.txt になっていること
        assert mock_upload.call_args[0][1][0][0] == "secret.txt"

