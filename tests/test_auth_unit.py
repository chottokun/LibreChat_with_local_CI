import pytest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import main

def test_get_api_key_valid():
    """Test get_api_key with a valid key using direct variable mocking."""
    with patch("main.API_KEY", "valid-test-key"):
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
        result = asyncio.run(main.get_api_key("valid-key", "invalid-key"))
        assert result == "valid-key"

def test_get_api_key_header_invalid_query_valid():
    """Test that if an invalid header is provided, it fails even if a valid query parameter is also provided."""
    with patch("main.API_KEY", "valid-key"):
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(main.get_api_key("invalid-key", "valid-key"))
        assert excinfo.value.status_code == 401

def test_get_api_key_query_fallback():
    """Test that if no header is provided, it correctly uses a valid query parameter."""
    with patch("main.API_KEY", "valid-key"):
        result = asyncio.run(main.get_api_key(None, "valid-key"))
        assert result == "valid-key"

def test_get_api_key_both_missing():
    """Test that if neither header nor query parameter is provided, it fails."""
    with patch("main.API_KEY", "valid-key"):
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(main.get_api_key(None, None))
        assert excinfo.value.status_code == 401
