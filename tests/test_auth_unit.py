import pytest
import asyncio
from unittest.mock import patch, MagicMock

# NOTE: The following mocks are necessary to run unit tests in an environment
# where full dependencies (FastAPI, Docker) are not installed.
# This follows the project's internal testing guidelines for restricted environments.
import sys

# Define a mock HTTPException class for use if fastapi is missing
class MockHTTPException(Exception):
    def __init__(self, status_code, detail=None, headers=None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

if "fastapi" not in sys.modules:
    mock_fastapi = MagicMock()
    mock_fastapi.HTTPException = MockHTTPException
    sys.modules["fastapi"] = mock_fastapi
    sys.modules["fastapi.security"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["docker"] = MagicMock()
    sys.modules["pydantic"] = MagicMock()

# Now we can safely import from main
import main
from fastapi import HTTPException

def test_get_api_key_valid():
    """Test get_api_key with a valid key using direct variable mocking."""
    # Mocking the API_KEY directly in the module is a clean way to test the logic
    # independent of the environment configuration.
    with patch("main.API_KEY", "valid-test-key"):
        # Since get_api_key is an async function, we use asyncio.run
        # because pytest-asyncio is not available.
        result = asyncio.run(main.get_api_key("valid-test-key"))
        assert result == "valid-test-key"

def test_get_api_key_invalid():
    """Test get_api_key with an invalid key."""
    with patch("main.API_KEY", "valid-test-key"):
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(main.get_api_key("wrong-key"))
        assert excinfo.value.status_code == 401
        assert excinfo.value.detail == "Invalid API Key"
