# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY

client = TestClient(app)

def test_language_validation_unsupported():
    """サポートされていない言語（例: javascript）での実行要求に対して400エラーが返されることを検証。"""
    headers = {"X-API-Key": API_KEY}
    response = client.post(
        "/exec",
        json={
            "code": "console.log('hello')",
            "lang": "javascript",
            "session_id": "test-lang-validation"
        },
        headers=headers
    )
    assert response.status_code == 400
    assert "Unsupported language" in response.json()["detail"]

def test_language_validation_supported():
    """サポートされている言語（例: python, py, bash, sh, r）で正常に処理されることを検証。"""
    # モックを使用してDocker実行は回避
    from unittest.mock import patch, MagicMock
    with patch("main.DOCKER_CLIENT") as mock_client:
        mock_container = MagicMock()
        mock_exec_res = MagicMock()
        mock_exec_res.exit_code = 0
        mock_exec_res.output = (b"stdout", b"stderr")
        mock_container.exec_run.return_value = mock_exec_res
        mock_client.containers.run.return_value = mock_container

        headers = {"X-API-Key": API_KEY}
        for lang in ["python", "py", "bash", "sh", "r", "R"]:
            response = client.post(
                "/exec",
                json={
                    "code": "some code",
                    "lang": lang,
                    "session_id": f"test-lang-{lang}"
                },
                headers=headers
            )
            assert response.status_code == 200

def test_session_mapping_helper_new_session():
    """新しいセッションに対して、スレッドセーフに双方向マッピングが生成されることを検証。"""
    nanoid = "new-nanoid-123"
    
    # 既存マッピングをクリアしてテスト
    with kernel_manager.lock:
        if nanoid in kernel_manager.nanoid_to_session:
            del kernel_manager.nanoid_to_session[nanoid]
        
    real_uuid, resolved_nanoid = kernel_manager.get_or_create_session_mapping(nanoid)
    
    # 双方向マッピングの検証
    assert real_uuid != nanoid
    assert len(resolved_nanoid) == 21
    
    with kernel_manager.lock:
        assert kernel_manager.nanoid_to_session[nanoid] == real_uuid
        assert kernel_manager.nanoid_to_session[resolved_nanoid] == real_uuid
        assert kernel_manager.session_to_nanoid[real_uuid] == resolved_nanoid

def test_session_mapping_helper_existing_session():
    """既存のセッションマッピングが正しく解決されることを検証。"""
    nanoid = "existing-nanoid-456"
    
    # 登録
    real_uuid, resolved_nanoid = kernel_manager.get_or_create_session_mapping(nanoid)
    
    # 再度同じ nanoid で取得
    real_uuid_2, resolved_nanoid_2 = kernel_manager.get_or_create_session_mapping(nanoid)
    
    assert real_uuid == real_uuid_2
    assert resolved_nanoid == resolved_nanoid_2
    assert len(resolved_nanoid_2) == 21

def test_librechat_session_id_omission_generates_new_isolated_session():
    """セッションID未指定のexecリクエスト（user_idのみ指定）に対して、user_{user_id}共有バインドではなく独立した新規セッションが生成されることを検証。"""
    from unittest.mock import patch, MagicMock
    with patch("main.DOCKER_CLIENT") as mock_client:
        mock_container = MagicMock()
        mock_exec_res = MagicMock()
        mock_exec_res.exit_code = 0
        mock_exec_res.output = (b"stdout", b"stderr")
        mock_container.exec_run.return_value = mock_exec_res
        mock_client.containers.run.return_value = mock_container

        headers = {"X-API-Key": API_KEY}
        test_user_id = "12345"

        # 1. 1回目のexec（Chat 1）
        res1 = client.post(
            "/exec",
            json={
                "code": "print('ok')",
                "user_id": test_user_id
            },
            headers=headers
        )
        assert res1.status_code == 200
        sid1 = res1.json()["session_id"]
        assert len(sid1) == 21

        # 2. 2回目のexec（Chat 2）
        res2 = client.post(
            "/exec",
            json={
                "code": "print('ok')",
                "user_id": test_user_id
            },
            headers=headers
        )
        assert res2.status_code == 200
        sid2 = res2.json()["session_id"]
        assert len(sid2) == 21

        # チャット分離のため、同一user_idであっても別の新規セッションが生成されていることを確認
        assert sid1 != sid2
