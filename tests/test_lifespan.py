import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import main

@pytest.mark.asyncio
async def test_lifespan_function_direct():
    """
    lifespan 関数を非同期コンテキストマネージャとして直接呼び出すテスト。
    起動時に recover_containers が呼び出され、cleanup_loop が開始されることを検証します。
    """
    with patch("main.kernel_manager.recover_containers") as mock_recover, \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup:

        # クリーンアップループがキャンセルされるまで実行され続けるようにモックを作成
        async def mock_cleanup_coro():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import lifespan
        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            mock_recover.assert_called_once()
            mock_cleanup.assert_called_once()

        # コンテキストを抜ける際にタスクが適切にキャンセル・待機されることを確認します。


@pytest.mark.asyncio
async def test_lifespan_with_testclient():
    """
    FastAPI の TestClient を用いて、lifespan イベント全体が正常に動作するかテスト。
    アプリ起動時にコンテナ復旧とクリーンアップが呼び出され、
    終了時にはクリーンアップタスクがキャンセルされて適切なログが出力されることを検証します。
    """
    with patch("main.kernel_manager.recover_containers") as mock_recover, \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup, \
         patch("main.logger.info") as mock_logger_info:

        async def mock_cleanup_coro():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import app
        with TestClient(app) as client:
            # 起動時の処理の検証
            mock_recover.assert_called_once()
            mock_cleanup.assert_called_once()

            response = client.get("/health")
            assert response.status_code == 200

        # 終了後のシャットダウン処理のログ出力を検証
        mock_logger_info.assert_any_call("Cleanup task cancelled during shutdown.")


@pytest.mark.asyncio
async def test_lifespan_startup_recovery_internal_error():
    """
    起動時に recover_containers が内部でエラーを起こした場合でも、
    FastAPI の起動処理自体はブロックされず、クリーンアップループが正常に開始されることを検証します。
    """
    # Docker クライアントが例外を投げるようにモック化し、recover_containers での内部例外をシミュレート
    with patch("main.DOCKER_CLIENT.containers.list", side_effect=Exception("Docker list failed")), \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup:

        async def mock_cleanup_coro():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import app
        # recover_containers のモックは行わず、実際の内部例外を発生させて lifespan を続行させる
        with TestClient(app) as client:
            mock_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_error_handling_during_shutdown():
    """
    シャットダウン中にクリーンアップループが CancelledError を発生させた場合に、
    それが正常に捕捉されて「Cleanup task cancelled during shutdown.」とログ出力されることを検証します。
    """
    with patch("main.kernel_manager.recover_containers") as mock_recover, \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup, \
         patch("main.logger.info") as mock_logger_info:

        async def mock_cleanup_coro():
            raise asyncio.CancelledError()

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import lifespan
        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            pass

        # キャンセル時のログが記録されているか検証
        mock_logger_info.assert_any_call("Cleanup task cancelled during shutdown.")


@pytest.mark.asyncio
async def test_lifespan_shutdown_exception_handling():
    """
    シャットダウン中にクリーンアップループが CancelledError 以外の予期せぬ例外を投げた場合、
    その例外がキャッチされずに上位へ正しく伝播することを確認します。
    """
    with patch("main.kernel_manager.recover_containers"), \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup, \
         patch("main.logger.info"):

        async def mock_cleanup_coro():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                # CancelledError の代わりに RuntimeError を発生させる
                raise RuntimeError("Unexpected error during cancellation")

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import app
        with pytest.raises(RuntimeError, match="Unexpected error during cancellation"):
            with TestClient(app) as client:
                pass
