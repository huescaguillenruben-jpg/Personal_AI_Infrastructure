import time
import unittest

from pailab.tds import ACS


class TestACS(unittest.TestCase):
    def test_happy_path(self):
        acs = ACS()
        cid, otp = acs.initiate("4111111111111111", 250_00)
        r = acs.verify(cid, otp)
        self.assertTrue(r.success)
        self.assertEqual(r.eci, "05")
        self.assertTrue(acs.verify_cavv(r.cavv, "4111111111111111", 250_00, cid))

    def test_bad_otp(self):
        acs = ACS()
        cid, _ = acs.initiate("4111111111111111", 250_00)
        r = acs.verify(cid, "000000")
        self.assertFalse(r.success)

    def test_consume_once(self):
        acs = ACS()
        cid, otp = acs.initiate("4111111111111111", 250_00)
        r = acs.verify(cid, otp)
        self.assertTrue(r.success)
        r2 = acs.verify(cid, otp)
        self.assertFalse(r2.success)

    def test_cavv_binds_to_amount(self):
        acs = ACS()
        cid, otp = acs.initiate("4111111111111111", 250_00)
        r = acs.verify(cid, otp)
        self.assertFalse(acs.verify_cavv(r.cavv, "4111111111111111", 999_00, cid))


if __name__ == "__main__":
    unittest.main()
