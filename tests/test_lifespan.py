import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
import main

@pytest.mark.asyncio
async def test_lifespan_management():
    """
    Verifies that the lifespan context manager:
    1. Calls recover_containers on startup.
    2. Starts the cleanup_loop background task.
    3. Properly cancels and awaits the cleanup task on shutdown.
    """
    # We need to mock recover_containers and cleanup_loop
    # Since cleanup_loop is an async function, we use AsyncMock
    with patch("main.kernel_manager.recover_containers") as mock_recover, \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup, \
         patch("main.logger.info") as mock_logger_info:

        # Define a side effect for cleanup_loop that stays alive until cancelled
        async def mock_cleanup_side_effect():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                # Re-raise to match expected behavior in main.py
                raise

        mock_cleanup.side_effect = mock_cleanup_side_effect

        # Using TestClient as a context manager triggers the lifespan events
        from main import app
        with TestClient(app) as client:
            # Verify startup actions
            mock_recover.assert_called_once()
            mock_cleanup.assert_called_once()

        # After exiting the context manager, shutdown logic has run
        # We check if the logger info was called for cancellation
        # "Cleanup task cancelled during shutdown."
        mock_logger_info.assert_any_call("Cleanup task cancelled during shutdown.")

@pytest.mark.asyncio
async def test_lifespan_startup_recovery_internal_error():
    """
    Verifies that if recover_containers encounters an internal error (caught by its own try-except),
    the lifespan continues and starts the cleanup task.
    """
    # To test internal error handling of recover_containers, we mock DOCKER_CLIENT.containers.list
    with patch("main.DOCKER_CLIENT.containers.list", side_effect=Exception("Docker list failed")), \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup:

        async def mock_cleanup_side_effect():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        mock_cleanup.side_effect = mock_cleanup_side_effect

        from main import app
        # We don't mock recover_containers here, we let it run and fail internally
        with TestClient(app) as client:
            mock_cleanup.assert_called_once()

@pytest.mark.asyncio
async def test_lifespan_shutdown_exception_handling():
    """
    Verifies that if the cleanup task raises something other than CancelledError during shutdown,
    it is logged or handled (though main.py currently only catches CancelledError).
    """
    with patch("main.kernel_manager.recover_containers"), \
         patch("main.kernel_manager.cleanup_loop", new_callable=AsyncMock) as mock_cleanup, \
         patch("main.logger.info"):

        # cleanup_loop raises a different error when cancelled
        async def mock_cleanup_side_effect():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise RuntimeError("Unexpected error during cancellation")

        mock_cleanup.side_effect = mock_cleanup_side_effect

        from main import app
        # TestClient will propagate exceptions from lifespan shutdown if they are not caught
        with pytest.raises(RuntimeError, match="Unexpected error during cancellation"):
            with TestClient(app) as client:
                pass
