import unittest

from pailab.crypto import HSM, const_time_eq, random_key


class TestHSM(unittest.TestCase):
    def setUp(self):
        self.hsm = HSM()

    def test_cvv_roundtrip(self):
        cvv = self.hsm.gen_cvv("4532191234567890", "12/29")
        self.assertEqual(len(cvv), 3)
        self.assertTrue(self.hsm.verify_cvv("4532191234567890", "12/29", cvv))
        self.assertFalse(self.hsm.verify_cvv("4532191234567890", "12/29", "000"))

    def test_cvv_depends_on_pan(self):
        a = self.hsm.gen_cvv("4111111111111111", "01/30")
        b = self.hsm.gen_cvv("4111111111111112", "01/30")
        # En teoria pueden colisionar 1/1000, pero diferentes inputs deberia
        # dar diferente la mayor parte del tiempo. Hacemos un test mas robusto:
        # con 5 pares distintos al menos uno debe diferir.
        diffs = 0
        for i in range(20):
            x = self.hsm.gen_cvv(f"45321912345678{i:02d}", "12/29")
            y = self.hsm.gen_cvv(f"45321912345679{i:02d}", "12/29")
            if x != y:
                diffs += 1
        self.assertGreater(diffs, 15)

    def test_arqc_roundtrip(self):
        un = b"\xde\xad\xbe\xef"
        arqc = self.hsm.compute_arqc(
            "4532191111111111", 1, atc=5, un=un,
            amount_minor=12500, currency="MXN", country="MX", mcc="5812",
        )
        self.assertEqual(len(arqc), 16)
        self.assertTrue(self.hsm.verify_arqc(
            arqc, "4532191111111111", 1, 5, un, 12500, "MXN", "MX", "5812",
        ))

    def test_arqc_tampering_detected(self):
        un = b"\x00\x00\x00\x01"
        arqc = self.hsm.compute_arqc(
            "4532191111111111", 1, atc=5, un=un,
            amount_minor=10000, currency="MXN", country="MX", mcc="5812",
        )
        # Cambiar el monto deberia invalidar el ARQC.
        self.assertFalse(self.hsm.verify_arqc(
            arqc, "4532191111111111", 1, 5, un, 99999, "MXN", "MX", "5812",
        ))

    def test_token_cryptogram(self):
        k = random_key()
        c = self.hsm.compute_token_cryptogram(k, "9999001234567890", 10000, "abc")
        self.assertTrue(self.hsm.verify_token_cryptogram(c, k, "9999001234567890", 10000, "abc"))
        self.assertFalse(self.hsm.verify_token_cryptogram(c, k, "9999001234567890", 10001, "abc"))

    def test_const_time_eq(self):
        self.assertTrue(const_time_eq("abc", "abc"))
        self.assertFalse(const_time_eq("abc", "abd"))


if __name__ == "__main__":
    unittest.main()
