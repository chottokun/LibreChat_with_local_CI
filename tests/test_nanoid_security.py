import pytest
from unittest.mock import patch
import main
from main import generate_nanoid

@pytest.mark.parametrize("size", [10, 21, 32])
def test_nanoid_length(size):
    nanoid = generate_nanoid(size)
    assert len(nanoid) == size

def test_nanoid_alphabet():
    alphabet = main._NANOID_ALPHABET
    nanoid = generate_nanoid(1000)
    for char in nanoid:
        assert char in alphabet

def test_nanoid_is_secure():
    # We check if secrets.choice is being used
    # We need to patch main.secrets.choice because that's what generate_nanoid uses
    with patch('main.secrets.choice', side_effect=lambda x: x[0]) as mock_choice:
        nanoid = generate_nanoid(5)
        assert mock_choice.call_count == 5
        alphabet = main._NANOID_ALPHABET
        assert nanoid == alphabet[0] * 5
