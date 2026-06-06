import pytest
import threading
import time
import os
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

# Set API KEY before importing main to avoid validation error
os.environ["LIBRECHAT_CODE_API_KEY"] = "test-key"
from main import KernelManager

def test_parallel_container_creation_respects_max_sessions():
    """
    Test that when multiple threads attempt to create containers simultaneously,
    the RCE_MAX_SESSIONS capacity limit is strictly enforced and no excess containers are run.
    This verifies that the pending_sessions logic successfully prevents race conditions.
    """
    km = KernelManager()
    km.active_kernels = {}
    km.pending_sessions = set()
    
    # Set capacity limit to 2
    from main import RCE_MAX_SESSIONS
    with patch("main.RCE_MAX_SESSIONS", 2):
        # We mock DOCKER_CLIENT.containers.run to simulate a slow Docker startup (0.1s delay)
        mock_docker_client = MagicMock()
        
        container_run_calls = 0
        container_run_lock = threading.Lock()
        
        def slow_run(*args, **kwargs):
            nonlocal container_run_calls
            with container_run_lock:
                container_run_calls += 1
            # Simulate Docker API latency
            time.sleep(0.1)
            mock_container = MagicMock()
            mock_container.id = f"mock_container_{container_run_calls}"
            return mock_container
            
        mock_docker_client.containers.run.side_effect = slow_run
        
        with patch("main.DOCKER_CLIENT", mock_docker_client):
            results = []
            threads = []
            
            def attempt_start(session_id):
                try:
                    km.start_new_container(session_id)
                    results.append(("success", session_id))
                except HTTPException as e:
                    results.append(("error", session_id, e.status_code))
                except Exception as e:
                    results.append(("exception", session_id, str(e)))
            
            # Start 3 threads simultaneously for 3 different sessions
            for i in range(3):
                t = threading.Thread(target=attempt_start, args=(f"session_{i}",))
                threads.append(t)
                
            for t in threads:
                t.start()
                
            for t in threads:
                t.join()
                
            # Analysis of results
            success_count = sum(1 for r in results if r[0] == "success")
            error_count = sum(1 for r in results if r[0] == "error" and r[2] == 503)
            
            print(f"Results: {results}")
            print(f"Docker run calls: {container_run_calls}")
            
            # Exactly 2 should succeed, 1 should fail with 503 (Server at capacity)
            assert success_count == 2
            assert error_count == 1
            # Docker run should have only been called 2 times
            assert container_run_calls == 2
            # Pending sessions list should be clean
            assert len(km.pending_sessions) == 0
            # Active kernels should have exactly 2 sessions
            assert len(km.active_kernels) == 2
