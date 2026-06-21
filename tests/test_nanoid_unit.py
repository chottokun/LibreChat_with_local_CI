import pytest
from unittest.mock import patch
from main import generate_nanoid, _NANOID_ALPHABET

def test_generate_nanoid_default_size():
    """Test that generate_nanoid returns a string of default size 21."""
    nanoid = generate_nanoid()
    assert isinstance(nanoid, str)
    assert len(nanoid) == 21

@pytest.mark.parametrize("size", [0, 1, 10, 50, 100])
def test_generate_nanoid_custom_size(size):
    """Test that generate_nanoid returns a string of the requested size."""
    nanoid = generate_nanoid(size=size)
    assert len(nanoid) == size

def test_generate_nanoid_alphabet():
    """Test that generate_nanoid only uses characters from _NANOID_ALPHABET."""
    # Use a large size to increase probability of seeing many characters
    nanoid = generate_nanoid(1000)
    for char in nanoid:
        assert char in _NANOID_ALPHABET

def test_generate_nanoid_uniqueness():
    """Test that multiple calls to generate_nanoid produce different results (probabilistic)."""
    # Highly unlikely to get two identical 21-char NanoIDs
    id1 = generate_nanoid()
    id2 = generate_nanoid()
    assert id1 != id2

def test_generate_nanoid_cryptographically_secure():
    """Test that generate_nanoid uses secrets.choice for cryptographic security."""
    with patch("main.secrets.choice") as mock_choice:
        # Mock choice to always return the first character for predictability
        mock_choice.side_effect = lambda x: x[0]

        size = 10
        nanoid = generate_nanoid(size=size)

        assert nanoid == _NANOID_ALPHABET[0] * size
        assert mock_choice.call_count == size
        # Verify it's called with the correct alphabet
        mock_choice.assert_called_with(_NANOID_ALPHABET)

def test_generate_nanoid_negative_size():
    """Test behavior with negative size (expected to be empty string)."""
    # In the current implementation:
    # ''.join(secrets.choice(_NANOID_ALPHABET) for _ in range(size))
    # range(-1) is empty, so it should return an empty string.
    assert generate_nanoid(-1) == ""
