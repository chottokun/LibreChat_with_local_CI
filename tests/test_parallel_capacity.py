import threading
import os
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

# Set API KEY before importing main to avoid validation error
os.environ["LIBRECHAT_CODE_API_KEY"] = "test-key"
from main import KernelManager  # noqa: E402

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
    with patch("main.RCE_MAX_SESSIONS", 2):
        # We mock DOCKER_CLIENT.containers.run to simulate a slow Docker startup
        mock_docker_client = MagicMock()
        
        container_run_calls = 0
        container_run_lock = threading.Lock()
        
        # Coordination events
        # signaled when the required number of threads are inside the mock
        threads_started = threading.Event()
        # signaled when threads are allowed to finish
        can_finish = threading.Event()

        def slow_run(*args, **kwargs):
            nonlocal container_run_calls
            with container_run_lock:
                container_run_calls += 1
                if container_run_calls == 2:
                    threads_started.set()

            # Wait until signaled to finish, or timeout to prevent deadlock
            can_finish.wait(timeout=2)

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
            
            # Start first 2 threads (to fill capacity)
            for i in range(2):
                t = threading.Thread(target=attempt_start, args=(f"session_{i}",))
                threads.append(t)
                t.start()

            # Wait for the first 2 threads to be "in progress" (holding capacity slots)
            if not threads_started.wait(timeout=2):
                raise RuntimeError("Timeout waiting for threads to start")

            # Start 3rd thread - should fail immediately as capacity is full (2 active/pending)
            t3 = threading.Thread(target=attempt_start, args=("session_2",))
            t3.start()
            t3.join()

            # Now allow the first 2 to finish
            can_finish.set()

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
