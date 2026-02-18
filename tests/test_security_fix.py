import unittest
import os
import docker
from unittest.mock import patch, MagicMock

class TestSecurityFix(unittest.TestCase):
    @patch('docker.api.client.APIClient._retrieve_server_version')
    def test_docker_client_initialization(self, mock_version):
        """
        Test that the Docker client is initialized using environment variables,
        which allows it to connect to the Docker Socket Proxy.
        """
        mock_version.return_value = "1.41"

        test_host = "tcp://docker-proxy:2375"
        with patch.dict(os.environ, {"DOCKER_HOST": test_host}):
            client = docker.from_env()
            # docker-py converts tcp:// to http:// for its internal base_url
            expected_url = "http://docker-proxy:2375"
            self.assertEqual(client.api.base_url, expected_url)
            print(f"Verified: Docker client configured to use {client.api.base_url}")

if __name__ == "__main__":
    unittest.main()
