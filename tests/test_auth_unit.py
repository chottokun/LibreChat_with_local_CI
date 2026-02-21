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

# Check if dependencies are available before mocking
try:
    import fastapi
    import docker
    import pydantic
    from fastapi import HTTPException
except ImportError:
    if "fastapi" not in sys.modules:
        mock_fastapi = MagicMock()
        mock_fastapi.HTTPException = MockHTTPException
        sys.modules["fastapi"] = mock_fastapi
        sys.modules["fastapi.security"] = MagicMock()
        sys.modules["fastapi.responses"] = MagicMock()
        sys.modules["docker"] = MagicMock()
        sys.modules["pydantic"] = MagicMock()
    from fastapi import HTTPException

# Now we can safely import from main
import main

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

def test_get_api_key_header_precedence():
    """Test that header takes precedence over query parameter when both are present and header is valid."""
    with patch("main.API_KEY", "valid-key"):
        # Header valid, query invalid -> should succeed because header is checked first
        result = asyncio.run(main.get_api_key("valid-key", "invalid-key"))
        assert result == "valid-key"

def test_get_api_key_header_invalid_query_valid():
    """Test that if an invalid header is provided, it fails even if a valid query parameter is also provided."""
    with patch("main.API_KEY", "valid-key"):
        # Header invalid, query valid -> should FAIL because header takes precedence
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(main.get_api_key("invalid-key", "valid-key"))
        assert excinfo.value.status_code == 401

def test_get_api_key_query_fallback():
    """Test that if no header is provided, it correctly uses a valid query parameter."""
    with patch("main.API_KEY", "valid-key"):
        # Header None, query valid -> should succeed
        result = asyncio.run(main.get_api_key(None, "valid-key"))
        assert result == "valid-key"

def test_get_api_key_both_missing():
    """Test that if neither header nor query parameter is provided, it fails."""
    with patch("main.API_KEY", "valid-key"):
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(main.get_api_key(None, None))
        assert excinfo.value.status_code == 401
