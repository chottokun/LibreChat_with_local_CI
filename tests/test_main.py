import sys
import asyncio
import pytest
from unittest.mock import MagicMock

# The environment for these tests may not have all dependencies (like fastapi, docker)
# installed. To allow unit testing the logic in main.py, we mock these dependencies
# in sys.modules before importing the module.
class MockHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail

if "fastapi" not in sys.modules:
    mock_fastapi = MagicMock()
    mock_fastapi.HTTPException = MockHTTPException
    sys.modules["fastapi"] = mock_fastapi
    sys.modules["fastapi.security"] = MagicMock()
    sys.modules["docker"] = MagicMock()
    sys.modules["pydantic"] = MagicMock()

# Now we can safely import main
import main

def test_get_api_key_valid():
    """Test get_api_key with the default valid key."""
    from main import get_api_key, API_KEY
    result = asyncio.run(get_api_key(API_KEY))
    assert result == API_KEY

def test_get_api_key_invalid():
    """Test get_api_key with an invalid key."""
    from main import get_api_key
    with pytest.raises(MockHTTPException) as excinfo:
        asyncio.run(get_api_key("invalid_key"))

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid API Key"

def test_get_api_key_custom_env(monkeypatch):
    """Test get_api_key with a custom key set via environment variable."""
    import importlib
    custom_key = "my_new_secret"
    # Set the environment variable and reload main to pick up the new value
    monkeypatch.setenv("CUSTOM_RCE_API_KEY", custom_key)
    importlib.reload(main)

    from main import get_api_key, API_KEY
    assert API_KEY == custom_key
    result = asyncio.run(get_api_key(custom_key))
    assert result == custom_key
