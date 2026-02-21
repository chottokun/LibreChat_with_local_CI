import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Mock docker before importing main
sys.modules['docker'] = MagicMock()

import main

class TestHappyPath(unittest.TestCase):
    @patch('main.kernel_manager')
    def test_run_code_success(self, mock_kernel_manager):
        # Setup mock attributes
        mock_kernel_manager.session_to_nanoid = {}
        mock_kernel_manager.nanoid_to_session = {}
        mock_kernel_manager.file_id_map = {}

        # Setup mock methods
        mock_kernel_manager.execute_code.return_value = {
            "stdout": "hello world\n",
            "stderr": "",
            "exit_code": 0
        }

        from fastapi.testclient import TestClient
        client = TestClient(main.app)

        response = client.post(
            "/run/exec",
            headers={"X-API-Key": "your_secret_key"},
            json={"code": "print('hello world')", "session_id": "test_session"}
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200
        assert response.json()["stdout"] == "hello world\n"
        print("Happy path test passed!")

if __name__ == "__main__":
    # We need to install httpx for TestClient
    import subprocess
    try:
        import httpx
    except ImportError:
        subprocess.run(["pip", "install", "httpx"], check=True)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestHappyPath)
    unittest.TextTestRunner().run(suite)
