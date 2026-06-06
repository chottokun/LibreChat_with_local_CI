import asyncio
import time
import pytest
from main import app, kernel_manager
from unittest.mock import MagicMock
import httpx

# Mock execute_code to be slow
def slow_execute_code(*args, **kwargs):
    time.sleep(1)
    return {
        "stdout": "ok",
        "stderr": "",
        "exit_code": 0
    }

# Mock list_files to be fast
def mock_list_files(*args, **kwargs):
    return []

@pytest.mark.anyio
async def test_concurrent_exec_performance():
    # Setup mocks
    original_execute = kernel_manager.execute_code
    original_list = kernel_manager.list_files
    kernel_manager.execute_code = MagicMock(side_effect=slow_execute_code)
    kernel_manager.list_files = MagicMock(side_effect=mock_list_files)

    # We need to use a real server or something that can handle concurrent requests
    # TestClient is synchronous and won't show the event loop blocking
    # but we can use httpx with the app directly if we use ASGIClients

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        start_time = time.perf_counter()

        # Send 3 concurrent requests
        tasks = [
            client.post("/exec", json={"code": "print(1)", "session_id": f"s{i}"}, headers={"X-API-Key": "testkey"})
            for i in range(3)
        ]

        responses = await asyncio.gather(*tasks)
        end_time = time.perf_counter()

        total_time = end_time - start_time
        print(f"\nTotal time for 3 concurrent requests: {total_time:.2f}s")

        for resp in responses:
            assert resp.status_code == 200

    # Restore originals
    kernel_manager.execute_code = original_execute
    kernel_manager.list_files = original_list

if __name__ == "__main__":
    # To run this manually:
    # uv run pytest tests/benchmark_async.py
    pass
