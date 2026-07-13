import pytest
import main
import uuid
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    # Reset global state to ensure test isolation
    main.LAST_UPLOADED_SESSION_ID = None
    main.LAST_UPLOAD_TIME = 0
    # Clear kernel manager mappings
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_exec_fallback_to_last_upload():
    """
    Verify that the global LAST_UPLOADED_SESSION_ID set by /upload
    is correctly used as a fallback in /exec (L832-833).
    """
    with patch.object(kernel_manager, 'upload_files_batch'):
        with patch.object(kernel_manager, 'execute_code') as mock_exec:
            with patch.object(kernel_manager, 'list_files', return_value=[]):
                mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}

                # 1. Upload a file to establish a session
                session_id = "upload-session-fallback-test"
                client.post(
                    "/upload",
                    headers={"X-API-Key": API_KEY},
                    data={"session_id": session_id},
                    files=[("files", ("test.txt", b"hello"))]
                )

                assert main.LAST_UPLOADED_SESSION_ID == session_id

                # 2. Execute code without session_id - should fallback to session_id
                response = client.post(
                    "/exec",
                    headers={"X-API-Key": API_KEY},
                    json={"code": "print('hello')"}
                )

                assert response.status_code == 200
                assert response.json()["session_id"] == session_id
                mock_exec.assert_called_once()

def test_upload_multiple_files_one_invalid():
    """
    Verify that if any file in a multi-file upload has an invalid filename,
    the request returns a 400 error.
    """
    with patch.object(kernel_manager, 'upload_files_batch'):
        files = [
            ("files", ("valid.txt", b"content")),
            ("files", ("/", b"invalid")) # Basename is empty, should trigger 400
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=files
        )
        assert response.status_code == 400
        assert "Invalid filename" in response.json()["detail"]

def test_upload_special_characters_session_id_mapping():
    """
    Verify that session IDs with special characters are correctly sanitized internally
    but the original ID is preserved in the mapping and response.
    """
    with patch.object(kernel_manager, 'upload_files_batch') as mock_upload:
        special_sid = "session!@$ %^&*()"
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": special_sid},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == special_sid

        # Verify internal sanitization and UUID mapping
        mock_upload.assert_called_once()
        real_sid = mock_upload.call_args[0][0]
        # Should be a valid UUID
        uuid.UUID(real_sid)

        # Check mapping from sanitized nanoid
        sanitized_sid = main.sanitize_id(special_sid)
        with kernel_manager.lock:
            assert kernel_manager.nanoid_to_session[sanitized_sid] == real_sid
            assert kernel_manager.session_to_nanoid[real_sid] == sanitized_sid


def test_upload_parallel_no_session_id_reuses_same_session():
    """
    セッションIDが指定されていない並行アップロードにおいて、
    2回目以降のアップロードが最初のアップロードで生成されたセッションIDを
    正しく再利用することを検証します。
    """
    with patch.object(kernel_manager, 'upload_files_batch'):
        # 1. 最初のファイルをセッションIDなしでアップロード
        response1 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("first.txt", b"first file content"))]
        )
        assert response1.status_code == 200
        data1 = response1.json()
        sid1 = data1["session_id"]
        assert len(sid1) == 21  # Nanoid

        # 2. 2番目のファイルをセッションIDなしで即座にアップロード
        response2 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("second.txt", b"second file content"))]
        )
        assert response2.status_code == 200
        data2 = response2.json()
        sid2 = data2["session_id"]

        # 同一セッションにバインドされていることを確認
        assert sid1 == sid2


def test_exec_aggregates_files_from_different_sessions():
    """
    実行リクエスト（/exec）において、異なるセッションIDを持つ複数のファイルが渡された場合、
    それらが実行対象のセッション（コンテナ）へ自動的にコピー・集約されることを検証します。
    """
    with patch.object(kernel_manager, 'execute_code') as mock_exec:
        with patch.object(kernel_manager, 'list_files', return_value=[]):
            with patch.object(kernel_manager, 'download_file') as mock_download:
                with patch.object(kernel_manager, 'upload_file') as mock_upload:
                    mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}
                    # download_file は (content, mtime) を返す
                    mock_download.return_value = (b"file content", 0)

                    # /exec リクエストに異なるセッションIDのファイル情報を含める
                    response = client.post(
                        "/exec",
                        headers={"X-API-Key": API_KEY},
                        json={
                            "code": "print('hello')",
                            "session_id": "main-exec-session",
                            "files": [
                                {
                                    "id": "file-id-1",
                                    "name": "other.txt",
                                    "session_id": "other-session"
                                }
                            ]
                        }
                    )

                    assert response.status_code == 200
                    # 他のセッション (other-session) からのダウンロードが走ったことを確認
                    mock_download.assert_called_once()
                    assert mock_download.call_args[0][1] == "other.txt"

                    # 実行対象のセッション (main-exec-session) へのアップロードが走ったことを確認
                    mock_upload.assert_called_once()
                    assert mock_upload.call_args[0][1] == "other.txt"
