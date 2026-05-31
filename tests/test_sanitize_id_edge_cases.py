import pytest
from main import sanitize_id

def test_sanitize_id_none():
    """Test sanitize_id with None to ensure early return coverage."""
    # Note: Type hint says str, but runtime might pass None
    assert sanitize_id(None) == ""

def test_sanitize_id_empty_string():
    """Test sanitize_id with an empty string."""
    assert sanitize_id("") == ""

def test_sanitize_id_all_invalid_chars():
    """Test sanitize_id with a string containing only invalid characters."""
    # This should return an empty string after the loop, not via early return
    assert sanitize_id("!@#$%^&*()") == ""

def test_sanitize_id_mixed_valid_invalid():
    """Test sanitize_id with a mix of valid and invalid characters."""
    assert sanitize_id("valid-id_123!@#") == "valid-id_123"

def test_sanitize_id_only_valid():
    """Test sanitize_id with only valid characters."""
    assert sanitize_id("abcABC123-_") == "abcABC123-_"
