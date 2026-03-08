import pytest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app, startup_event, kernel_manager

def test_startup_event_direct():
    """Test the startup_event function directly."""
    with patch.object(kernel_manager, "recover_containers") as mock_recover, \
         patch.object(kernel_manager, "cleanup_loop", return_value=MagicMock()) as mock_cleanup, \
         patch("asyncio.create_task") as mock_create_task:

        # We need to run the async function
        asyncio.run(startup_event())

        mock_recover.assert_called_once()
        mock_create_task.assert_called_once()
        # Verify it was called with the cleanup_loop coroutine
        # Since cleanup_loop() returns a coroutine object, we check if it was called
        mock_cleanup.assert_called_once()

def test_startup_event_via_client():
    """Test the startup event via FastAPI TestClient's lifespan context."""
    with patch.object(kernel_manager, "recover_containers") as mock_recover, \
         patch.object(kernel_manager, "cleanup_loop", return_value=MagicMock()) as mock_cleanup, \
         patch("asyncio.create_task") as mock_create_task:

        # TestClient with 'with' block triggers 'startup' and 'shutdown' events
        with TestClient(app) as client:
            # When the client enters the context, startup events are fired
            pass

        mock_recover.assert_called_once()
        mock_create_task.assert_called_once()
        mock_cleanup.assert_called_once()
