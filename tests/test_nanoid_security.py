import unittest
from unittest.mock import patch
import main
from main import generate_nanoid

class TestNanoidSecurity(unittest.TestCase):
    def test_nanoid_length(self):
        for size in [10, 21, 32]:
            nanoid = generate_nanoid(size)
            self.assertEqual(len(nanoid), size)

    def test_nanoid_alphabet(self):
        alphabet = main._NANOID_ALPHABET
        nanoid = generate_nanoid(1000)
        for char in nanoid:
            self.assertIn(char, alphabet)

    def test_nanoid_is_secure(self):
        # We check if secrets.choice is being used
        # We need to patch main.secrets.choice because that's what generate_nanoid uses
        with patch('main.secrets.choice', side_effect=lambda x: x[0]) as mock_choice:
            nanoid = generate_nanoid(5)
            self.assertEqual(mock_choice.call_count, 5)
            alphabet = main._NANOID_ALPHABET
            self.assertEqual(nanoid, alphabet[0] * 5)

if __name__ == "__main__":
    unittest.main()
