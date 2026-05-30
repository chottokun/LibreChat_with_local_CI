import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import main

@pytest.mark.asyncio
async def test_lifespan_function_direct():
    """
    Test the lifespan function directly as an async context manager.
    This verifies that it calls recover_containers and starts cleanup_loop.
    """
    with patch("main.kernel_manager.recover_containers") as mock_recover, \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup:

        # Mock cleanup_loop to stay "running" until cancelled
        # By default AsyncMock will return immediately.
        # To simulate a long running task that can be cancelled:
        async def mock_cleanup_coro():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import lifespan
        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            mock_recover.assert_called_once()
            mock_cleanup.assert_called_once()
            # At this point, the task is running (sleeping in our mock)

        # When exiting the context manager, the task is cancelled and awaited.
        # If it wasn't cancelled properly, this test would hang or fail.

def test_lifespan_with_testclient():
    """
    Test the lifespan through FastAPI TestClient context manager.
    This ensures that the FastAPI application correctly triggers the lifespan events.
    """
    with patch("main.kernel_manager.recover_containers") as mock_recover, \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup:

        # We need a long-running mock to ensure it's still there when we yield
        async def mock_cleanup_coro():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass # Expected on shutdown

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import app
        # TestClient as a context manager triggers the lifespan
        with TestClient(app) as client:
            mock_recover.assert_called_once()
            mock_cleanup.assert_called_once()

            response = client.get("/health")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_lifespan_error_handling_during_shutdown():
    """
    Test that the lifespan handles CancelledError during shutdown gracefully.
    """
    with patch("main.kernel_manager.recover_containers") as mock_recover, \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup, \
         patch("main.logger") as mock_logger:

        async def mock_cleanup_coro():
            raise asyncio.CancelledError()

        mock_cleanup.side_effect = mock_cleanup_coro

        from main import lifespan
        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            pass

        # Verify that it logged the cancellation
        mock_logger.info.assert_any_call("Cleanup task cancelled during shutdown.")
