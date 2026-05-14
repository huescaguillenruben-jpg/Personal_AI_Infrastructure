import json
import time
import unittest

from pailab.errors import RC

from tests._world import make_world


class TestFraud(unittest.TestCase):
    def test_velocity_blocks_after_threshold(self):
        iss, acq, term, _, _, card = make_world()
        # Hace 5 ok luego rechazo
        for i in range(5):
            r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 10_00)
            self.assertEqual(r.get("RESPONSE_CODE"), RC.APPROVED.value)
        r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 10_00)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.EXCEEDS_FREQ_LIMIT.value)

    def test_repeated_declines_block_pan(self):
        iss, acq, term, _, _, card = make_world()
        # 5 intentos con CVV malo bloquean el PAN
        for _ in range(5):
            term.swipe(card.pan, card.expiry_mmYY, "000", 10_00)
        r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 10_00)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.RESTRICTED_CARD.value)

    def test_ecom_high_amount_requires_3ds(self):
        iss, acq, term, _, _, card = make_world(deposit_minor=10_000_00)
        r = term.ecommerce(card.pan, card.expiry_mmYY, card.cvv, 5_000_00)
        self.assertEqual(r.get("RESPONSE_CODE"),
                         RC.SOFT_DECLINE_SCA_REQUIRED.value)
        ecom = json.loads(r.get("ECOM_DATA"))
        self.assertIn("challenge_id", ecom)
        cid, otp = ecom["challenge_id"], ecom["otp_demo"]
        result = iss.acs.verify(cid, otp)
        self.assertTrue(result.success)
        r2 = term.ecommerce(card.pan, card.expiry_mmYY, card.cvv, 5_000_00,
                            cavv=result.cavv, cavv_cid=cid)
        self.assertEqual(r2.get("RESPONSE_CODE"), RC.APPROVED.value)


if __name__ == "__main__":
    unittest.main()
