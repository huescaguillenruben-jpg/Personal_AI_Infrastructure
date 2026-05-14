import unittest

from pailab.luhn import generate_pan, luhn_checksum_of_partial, luhn_valid


class TestLuhn(unittest.TestCase):
    def test_known_valid(self):
        # Numero de prueba famoso (no funciona en bancos: solo pasa Luhn).
        self.assertTrue(luhn_valid("4111111111111111"))
        self.assertTrue(luhn_valid("5555555555554444"))
        self.assertTrue(luhn_valid("378282246310005"))   # 15 digitos

    def test_known_invalid(self):
        self.assertFalse(luhn_valid("4111111111111112"))   # ultimo digito mal
        self.assertFalse(luhn_valid(""))
        self.assertFalse(luhn_valid("abc"))
        self.assertFalse(luhn_valid("12345678901"))    # demasiado corto

    def test_generate_passes_luhn(self):
        for _ in range(100):
            pan = generate_pan("453219")
            self.assertEqual(len(pan), 16)
            self.assertTrue(pan.startswith("453219"))
            self.assertTrue(luhn_valid(pan))

    def test_checksum_for_partial(self):
        # 411111111111111 + ? -> 1
        self.assertEqual(luhn_checksum_of_partial("411111111111111"), 1)

    def test_bad_bin(self):
        with self.assertRaises(ValueError):
            generate_pan("abc")
        with self.assertRaises(ValueError):
            generate_pan("12")     # demasiado corto


if __name__ == "__main__":
    unittest.main()
