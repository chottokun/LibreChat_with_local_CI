import pytest
import main
import uuid
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app, API_KEY, kernel_manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    # Clear kernel manager mappings
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield


def test_exec_without_session_creates_new_session():
    """
    セッションID未指定のexecリクエストが新規セッションを生成することを検証。
    チャット間セッション汚染の防止を確認する。
    """
    with patch.object(kernel_manager, "upload_files_batch"):
        with patch.object(kernel_manager, "execute_code") as mock_exec:
            with patch.object(kernel_manager, "list_files", return_value=[]):
                mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}

                # 1. アップロードでセッションを確立
                upload_session_id = "upload-session-isolation-test"
                client.post(
                    "/upload",
                    headers={"X-API-Key": API_KEY},
                    data={"session_id": upload_session_id},
                    files=[("files", ("test.txt", b"hello"))],
                )

                # 2. セッションID未指定でexec → 新規セッションが生成される
                response = client.post(
                    "/exec",
                    headers={"X-API-Key": API_KEY},
                    json={"code": "print('hello')"},
                )

                assert response.status_code == 200
                returned_sid = response.json()["session_id"]
                assert len(returned_sid) == 21

                # アップロードセッションとは別のセッションが生成されていることを確認
                real_upload_sid, _ = kernel_manager.get_or_create_session_mapping(
                    upload_session_id
                )
                real_exec_sid, _ = kernel_manager.get_or_create_session_mapping(
                    returned_sid
                )
                assert real_upload_sid != real_exec_sid


def test_exec_with_storage_session_id_reuses_session():
    """
    files[].storage_session_id を含むexecリクエストが、
    正しく既存セッションを再利用することを検証。
    同一チャット内のターン間でセッションが維持される動作を確認する。
    """
    with patch.object(kernel_manager, "execute_code") as mock_exec:
        with patch.object(kernel_manager, "list_files", return_value=[]):
            mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}

            # 既知のセッションIDで2回実行
            session_id = "same-chat-session"
            for _ in range(2):
                response = client.post(
                    "/exec",
                    headers={"X-API-Key": API_KEY},
                    json={
                        "code": "print('hello')",
                        "files": [
                            {
                                "id": "file1",
                                "name": "data.csv",
                                "storage_session_id": session_id,
                            }
                        ],
                    },
                )
                assert response.status_code == 200

            # 2回のexecが同じセッションUUIDで実行されたことを確認
            assert mock_exec.call_count == 2
            first_call_sid = mock_exec.call_args_list[0][0][0]
            second_call_sid = mock_exec.call_args_list[1][0][0]
            assert first_call_sid == second_call_sid


def test_upload_multiple_files_one_invalid():
    """
    Verify that if any file in a multi-file upload has an invalid filename,
    the request returns a 400 error.
    """
    with patch.object(kernel_manager, "upload_files_batch"):
        files = [
            ("files", ("valid.txt", b"content")),
            ("files", ("/", b"invalid")),  # Basename is empty, should trigger 400
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=files,
        )
        assert response.status_code == 400
        assert "Invalid filename" in response.json()["detail"]


def test_upload_special_characters_session_id_mapping():
    """
    Verify that session IDs with special characters are correctly sanitized internally
    but the original ID is preserved in the mapping and response.
    """
    with patch.object(kernel_manager, "upload_files_batch") as mock_upload:
        special_sid = "session!@$ %^&*()"
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": special_sid},
            files=[("files", ("test.txt", b"content"))],
        )
        assert response.status_code == 200
        returned_sid = response.json()["session_id"]
        assert len(returned_sid) == 21

        # Verify internal sanitization and UUID mapping
        mock_upload.assert_called_once()
        real_sid = mock_upload.call_args[0][0]
        # Should be a valid UUID
        uuid.UUID(real_sid)

        # Check mapping from sanitized nanoid
        sanitized_sid = main.sanitize_id(special_sid)
        with kernel_manager.lock:
            assert kernel_manager.nanoid_to_session[sanitized_sid] == real_sid
            assert kernel_manager.session_to_nanoid[real_sid] == returned_sid


def test_upload_multiple_requests_no_session_id_creates_distinct_sessions():
    """
    セッションIDが指定されていない複数回のアップロードにおいて、
    それぞれ独立した新規セッションIDが生成され、チャット間分離が維持されることを検証します。
    """
    with patch.object(kernel_manager, "upload_files_batch"):
        # 1. 最初のファイルをセッションIDなしでアップロード (Chat 1)
        response1 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("first.txt", b"first file content"))],
        )
        assert response1.status_code == 200
        data1 = response1.json()
        sid1 = data1["session_id"]
        assert len(sid1) == 21  # Nanoid

        # 2. 2番目のファイルをセッションIDなしでアップロード (Chat 2)
        response2 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("second.txt", b"second file content"))],
        )
        assert response2.status_code == 200
        data2 = response2.json()
        sid2 = data2["session_id"]
        assert len(sid2) == 21

        # 異なるセッションIDが割り振られ、チャット分離が維持されていることを確認
        assert sid1 != sid2


def test_exec_aggregates_files_from_different_sessions():
    """
    実行リクエスト（/exec）において、異なるセッションIDを持つ複数のファイルが渡された場合、
    それらが実行対象のセッション（コンテナ）へ自動的にコピー・集約されることを検証します。
    """
    with patch.object(kernel_manager, "execute_code") as mock_exec:
        with patch.object(kernel_manager, "list_files", return_value=[]):
            with patch.object(kernel_manager, "download_file") as mock_download:
                with patch.object(kernel_manager, "upload_file") as mock_upload:
                    mock_exec.return_value = {
                        "stdout": "ok",
                        "stderr": "",
                        "exit_code": 0,
                    }
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
                                    "session_id": "other-session",
                                }
                            ],
                        },
                    )

                    assert response.status_code == 200
                    # 他のセッション (other-session) からのダウンロードが走ったことを確認
                    mock_download.assert_called_once()
                    assert mock_download.call_args[0][1] == "other.txt"

                    # 実行対象のセッション (main-exec-session) へのアップロードが走ったことを確認
                    mock_upload.assert_called_once()
                    assert mock_upload.call_args[0][1] == "other.txt"


@pytest.mark.anyio
async def test_upload_parallel_concurrent_requests_create_distinct_sessions():
    """
    非同期クライアントを用いて、セッションIDなしのアップロードリクエストを
    同時に並行して送信（asyncio.gather）した際、
    それぞれのアップロードリクエストが独立した新規セッションIDを取得することを検証します。
    """
    import asyncio
    from httpx import AsyncClient, ASGITransport
    from main import app, API_KEY

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        headers = {"X-API-Key": API_KEY or "dummy-key"}
        res1_task = ac.post(
            "/upload",
            headers=headers,
            files={"files": ("file1.txt", b"file1 content")},
        )
        res2_task = ac.post(
            "/upload",
            headers=headers,
            files={"files": ("file2.txt", b"file2 content")},
        )

        with patch.object(kernel_manager, "upload_files_batch"):
            res1, res2 = await asyncio.gather(res1_task, res2_task)

        assert res1.status_code == 200
        assert res2.status_code == 200

        sid1 = res1.json()["session_id"]
        sid2 = res2.json()["session_id"]

        # それぞれの並行アップロードが独立したセッションIDを取得することを確認
        assert sid1 != sid2


def test_chat_isolation_prevents_cross_chat_data_spill():
    """
    Chat 1 でアップロード・生成されたファイルが、
    Chat 2 のアップロードおよびコード実行環境（/mnt/data/）へ漏洩しないことを検証します。
    """
    with patch.object(kernel_manager, "upload_files_batch"):
        with patch.object(kernel_manager, "execute_code") as mock_exec:
            with patch.object(kernel_manager, "list_files", return_value=["chat2_data.csv"]):
                mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}

                # 1. Chat 1 でファイルアップロード
                res1 = client.post(
                    "/upload",
                    headers={"X-API-Key": API_KEY},
                    files=[("files", ("chat1_secret.csv", b"secret_data"))],
                )
                assert res1.status_code == 200
                chat1_sid = res1.json()["session_id"]

                # 2. 別チャット (Chat 2) を開きファイルアップロード
                res2 = client.post(
                    "/upload",
                    headers={"X-API-Key": API_KEY},
                    files=[("files", ("chat2_data.csv", b"public_data"))],
                )
                assert res2.status_code == 200
                chat2_sid = res2.json()["session_id"]

                # チャット間のセッション分離を確認
                assert chat1_sid != chat2_sid

                # 3. Chat 2 でコード実行
                exec_res = client.post(
                    "/exec",
                    headers={"X-API-Key": API_KEY},
                    json={
                        "code": "import os; print(os.listdir('/mnt/data'))",
                        "files": [
                            {
                                "id": "f2",
                                "name": "chat2_data.csv",
                                "storage_session_id": chat2_sid,
                            }
                        ],
                    },
                )
                assert exec_res.status_code == 200
                exec_sid = exec_res.json()["session_id"]
                assert exec_sid == chat2_sid

                # Chat 2 のコード実行が Chat 1 の内部 UUID セッションにアクセスしていないことを検証
                real_chat1_uuid, _ = kernel_manager.get_or_create_session_mapping(chat1_sid)
                real_chat2_uuid, _ = kernel_manager.get_or_create_session_mapping(chat2_sid)
                exec_target_uuid = mock_exec.call_args[0][0]

                assert exec_target_uuid == real_chat2_uuid
                assert exec_target_uuid != real_chat1_uuid
