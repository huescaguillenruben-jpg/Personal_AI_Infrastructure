import unittest

from pailab.logging_utils import mask_pan, scrub


class TestPCIMasking(unittest.TestCase):
    def test_mask_pan(self):
        self.assertEqual(mask_pan("4532191234567890"), "453219******7890")
        self.assertEqual(mask_pan("378282246310005"), "378282*****0005")
        self.assertEqual(mask_pan(""), "")

    def test_scrub_pan(self):
        out = scrub("Auth para 4532191234567890 OK")
        self.assertNotIn("123456789", out)
        self.assertIn("4532196", "4532196" if "453219" in out else "no")
        self.assertIn("453219", out)
        self.assertIn("7890", out)

    def test_scrub_cvv(self):
        out = scrub("data cvv=123 amount=10")
        self.assertNotIn("cvv=123", out)
        self.assertIn("cvv=***", out)

    def test_scrub_does_not_destroy_normal_numbers(self):
        out = scrub("monto=12345")
        self.assertIn("12345", out)


if __name__ == "__main__":
    unittest.main()
