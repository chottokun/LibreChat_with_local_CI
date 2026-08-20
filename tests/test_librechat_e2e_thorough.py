import re
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app, kernel_manager, API_KEY

client = TestClient(app)
NANOID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{21}$")


def test_librechat_is_valid_id_strict_compliance():
    """LibreChatの isValidID (/^[A-Za-z0-9_-]{21}$/) に全てのIDが厳格に適合することを検証。"""
    headers = {"X-API-Key": API_KEY}

    # 1. session_id なしで /upload 呼び出し
    with patch.object(kernel_manager, "upload_files_batch") as mock_upload:
        mock_upload.return_value = ({"test_doc.pdf": "/mnt/data/test_doc.pdf"}, [])
        resp_upload = client.post(
            "/upload",
            headers=headers,
            files=[("files", ("test_doc.pdf", b"PDF Content"))],
        )
        assert resp_upload.status_code == 200
        upload_data = resp_upload.json()
        upload_sid = upload_data["session_id"]

        # セッションIDが 21文字の Nanoid
        assert len(upload_sid) == 21
        assert NANOID_PATTERN.match(upload_sid)

        # 返却された files リストが存在すること
        assert "files" in upload_data
        assert len(upload_data["files"]) == 1


def test_librechat_exec_file_generation_and_download_flow():
    """LibreChatからのコード実行でファイル生成→ダウンロードのフルフロー検証。"""
    headers = {"X-API-Key": API_KEY}
    provided_sid = "user_chat_session_9999"  # 非21文字のユーザーセッションID

    mock_exec_result = {
        "stdout": "Data generated successfully\n",
        "stderr": "",
        "exit_code": 0,
    }

    with (
        patch.object(kernel_manager, "execute_code", return_value=mock_exec_result),
        patch.object(
            kernel_manager, "list_files", return_value=["output.csv", "summary.txt"]
        ),
        patch.object(
            kernel_manager,
            "get_file_id_mapping",
            return_value={
                "output.csv": "nanoid_csv_id_21char1",
                "summary.txt": "nanoid_txt_id_21char2",
            },
        ),
    ):
        resp_exec = client.post(
            "/exec",
            headers=headers,
            json={
                "code": "import pandas as pd\nprint('Data generated successfully')",
                "language": "python",
                "session_id": provided_sid,
            },
        )
        assert resp_exec.status_code == 200
        exec_data = resp_exec.json()

        # レスポンスの session_id は LibreChat 互換の 21文字 Nanoid に変換されている
        returned_sid = exec_data["session_id"]
        assert len(returned_sid) == 21
        assert NANOID_PATTERN.match(returned_sid)
        assert exec_data["status"] == "success"
        assert "Data generated successfully" in exec_data["output"]

        # 生成ファイルの検証
        files = exec_data["files"]
        assert len(files) == 2
        for f in files:
            file_id = f["id"]
            assert len(file_id) == 21
            assert NANOID_PATTERN.match(file_id)
            assert f["url"].startswith(f"/api/files/code/download/{returned_sid}/")


def test_librechat_session_omission_creates_isolated_session():
    """session_id なしの exec が、直前のアップロードセッションとは独立した新規セッションを生成することを検証。

    チャット間セッション汚染の防止を目的とした設計変更により、
    LAST_UPLOADED_SESSION_ID へのフォールバックは exec では無効化されている。
    """
    headers = {"X-API-Key": API_KEY}

    # 1. /upload でファイルアップロード (session_id 指定なし)
    with patch.object(kernel_manager, "upload_files_batch") as mock_upload:
        mock_upload.return_value = ({"data.json": "/mnt/data/data.json"}, [])
        resp_upload = client.post(
            "/upload",
            headers=headers,
            files=[("files", ("data.json", b'{"key": "value"}'))],
        )
        assert resp_upload.status_code == 200
        upload_sid = resp_upload.json()["session_id"]
        assert len(upload_sid) == 21

    # 2. 直後に /exec を session_id なしで送信
    mock_exec_result = {"stdout": "JSON parsed\n", "stderr": "", "exit_code": 0}

    with (
        patch.object(kernel_manager, "execute_code", return_value=mock_exec_result),
        patch.object(kernel_manager, "list_files", return_value=[]),
        patch.object(kernel_manager, "get_file_id_mapping", return_value={}),
    ):
        resp_exec = client.post(
            "/exec",
            headers=headers,
            json={
                "code": "import json; data = json.load(open('data.json')); print('JSON parsed')",
                "language": "python",
                # session_id なし
            },
        )
        assert resp_exec.status_code == 200
        exec_sid = resp_exec.json()["session_id"]

        # チャット分離: session_id なしの exec は新規セッションを生成し、
        # 直前のアップロードセッションとは異なるIDを返す
        assert exec_sid != upload_sid
        assert len(exec_sid) == 21


def test_librechat_session_continuity_via_storage_session_id():
    """
    同一チャット内で files[].storage_session_id を経由してターン間のセッション継続性が
    正常に維持されることを検証。
    1. /upload でファイルアップロード -> session_id (Session_A) 取得
    2. Turn 1 exec で storage_session_id: Session_A を指定 -> Session_A で実行
    3. Turn 2 exec で Turn 1 の生成ファイル (storage_session_id: Session_A) を指定 -> Session_A で継続実行
    """
    headers = {"X-API-Key": API_KEY}

    # 1. Upload
    with patch.object(kernel_manager, "upload_files_batch") as mock_upload:
        mock_upload.return_value = ({"input.csv": "/mnt/data/input.csv"}, [])
        resp_upload = client.post(
            "/upload",
            headers=headers,
            files=[("files", ("input.csv", b"col1,col2\n1,2"))],
        )
        assert resp_upload.status_code == 200
        sid_upload = resp_upload.json()["session_id"]
        assert len(sid_upload) == 21

    # 2. Turn 1 Exec (with storage_session_id)
    mock_exec_1 = {"stdout": "Processed input.csv\n", "stderr": "", "exit_code": 0}
    with (
        patch.object(kernel_manager, "execute_code", return_value=mock_exec_1) as mock_exec_fn,
        patch.object(kernel_manager, "list_files", return_value=["input.csv", "result.csv"]),
        patch.object(
            kernel_manager,
            "get_file_id_mapping",
            return_value={"input.csv": "id1_21char_nanoid_val1", "result.csv": "id2_21char_nanoid_val2"},
        ),
    ):
        resp_turn1 = client.post(
            "/exec",
            headers=headers,
            json={
                "code": "import pandas as pd; pd.read_csv('input.csv').to_csv('result.csv')",
                "files": [
                    {
                        "id": "id1_21char_nanoid_val1",
                        "name": "input.csv",
                        "storage_session_id": sid_upload,
                    }
                ],
            },
        )
        assert resp_turn1.status_code == 200
        turn1_sid = resp_turn1.json()["session_id"]
        assert turn1_sid == sid_upload

    # 3. Turn 2 Exec (continuing the same chat with storage_session_id)
    mock_exec_2 = {"stdout": "Analyzed result.csv\n", "stderr": "", "exit_code": 0}
    with (
        patch.object(kernel_manager, "execute_code", return_value=mock_exec_2) as mock_exec_fn,
        patch.object(kernel_manager, "list_files", return_value=["input.csv", "result.csv"]),
        patch.object(
            kernel_manager,
            "get_file_id_mapping",
            return_value={"input.csv": "id1_21char_nanoid_val1", "result.csv": "id2_21char_nanoid_val2"},
        ),
    ):
        resp_turn2 = client.post(
            "/exec",
            headers=headers,
            json={
                "code": "import pandas as pd; print(pd.read_csv('result.csv'))",
                "files": [
                    {
                        "id": "id2_21char_nanoid_val2",
                        "name": "result.csv",
                        "storage_session_id": turn1_sid,
                    }
                ],
            },
        )
        assert resp_turn2.status_code == 200
        turn2_sid = resp_turn2.json()["session_id"]
        # 同一チャット内での継続性が正常に維持されていることの検証
        assert turn2_sid == sid_upload


def test_librechat_download_endpoint_headers():
    """LibreChatバックエンドがダウンロードする際のヘッダー挙動を検証。"""
    headers = {"X-API-Key": API_KEY}
    raw_sid = "test_download_session_01"
    real_uuid, nanoid_sid = kernel_manager.get_or_create_session_mapping(raw_sid)

    # モックのダウンロードファイル設定 (content, mtime)
    with patch.object(kernel_manager, "download_file") as mock_dl:
        mock_dl.return_value = (b"dummy image data", 1700000000.0)

        response = client.get(
            f"/api/files/code/download/{nanoid_sid}/chart_output.png", headers=headers
        )

        assert response.status_code == 200
        # 画像・ファイルダウンロードレスポンスにはインライン表示を阻害する CSP ヘッダーが付与されないこと
        assert "Content-Security-Policy" not in response.headers
        assert response.headers["Content-Type"] == "image/png"
        assert response.content == b"dummy image data"
