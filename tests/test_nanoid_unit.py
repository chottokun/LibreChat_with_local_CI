import pytest
from unittest.mock import patch
import main
from main import generate_nanoid

def test_nanoid_default_size():
    """Verify that the default size is 21."""
    nanoid = generate_nanoid()
    assert len(nanoid) == 21

@pytest.mark.parametrize("size", [0, 1, 10, 50, 100])
def test_nanoid_custom_size(size):
    """Verify that custom sizes are respected."""
    nanoid = generate_nanoid(size)
    assert len(nanoid) == size

def test_nanoid_negative_size():
    """Verify that negative sizes return an empty string."""
    nanoid = generate_nanoid(-5)
    assert nanoid == ""

def test_nanoid_alphabet():
    """Verify that the generated string only contains characters from the allowed alphabet."""
    # Using a large size to increase coverage of the alphabet
    nanoid = generate_nanoid(1000)
    alphabet_set = set(main._NANOID_ALPHABET)
    for char in nanoid:
        assert char in alphabet_set

def test_nanoid_cryptographic_security():
    """Verify that secrets.choice is used for selection, ensuring cryptographic security."""
    with patch('main.secrets.choice', side_effect=lambda x: x[0]) as mock_choice:
        nanoid = generate_nanoid(5)
        assert mock_choice.call_count == 5
        # Since we mocked choice to always return the first character:
        expected = main._NANOID_ALPHABET[0] * 5
        assert nanoid == expected

def test_nanoid_uniqueness():
    """Verify that multiple calls produce different results (statistical check)."""
    results = set()
    for _ in range(100):
        results.add(generate_nanoid(21))
    assert len(results) == 100
