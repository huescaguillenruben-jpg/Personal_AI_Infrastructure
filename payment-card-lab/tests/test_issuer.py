import unittest

from pailab.errors import RC
from pailab.lifecycle import CardStatus
from tests._world import make_world


class TestIssuer(unittest.TestCase):
    def test_swipe_approved(self):
        iss, acq, term, _, acc, card = make_world()
        r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 100_00)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.APPROVED.value)
        self.assertEqual(acc.held_minor, 100_00)
        self.assertEqual(acc.available_minor(), 900_00)

    def test_swipe_bad_cvv(self):
        iss, acq, term, _, _, card = make_world()
        r = term.swipe(card.pan, card.expiry_mmYY, "000", 100_00)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.INVALID_CVV.value)

    def test_swipe_insufficient(self):
        iss, acq, term, _, _, card = make_world()
        r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 5_000_00)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.INSUFFICIENT_FUNDS.value)

    def test_card_stolen_blocks(self):
        iss, acq, term, _, _, card = make_world()
        iss.set_card_status(card.pan, CardStatus.STOLEN)
        r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 10_00)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.STOLEN_CARD.value)

    def test_emv_replay_blocked(self):
        iss, acq, term, _, _, card = make_world()
        r1 = term.chip(card.pan, card.expiry_mmYY, 100_00,
                       card_hsm=iss.hsm, atc=1, psn=card.card_seq_num)
        self.assertEqual(r1.get("RESPONSE_CODE"), RC.APPROVED.value)
        r2 = term.chip(card.pan, card.expiry_mmYY, 100_00,
                       card_hsm=iss.hsm, atc=1, psn=card.card_seq_num)
        self.assertEqual(r2.get("RESPONSE_CODE"), RC.CRYPTO_FAILURE.value)

    def test_capture_and_reverse(self):
        iss, acq, term, _, acc, card = make_world()
        r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 100_00)
        txn_id = r.get("ADDITIONAL")
        self.assertEqual(acc.held_minor, 100_00)
        iss.capture(txn_id)
        self.assertEqual(acc.posted_minor, 900_00)
        self.assertEqual(acc.held_minor, 0)
        # No se puede reversar despues de capture y refund:
        iss.refund(txn_id)
        self.assertEqual(acc.posted_minor, 1_000_00)

    def test_reverse_before_capture(self):
        iss, acq, term, _, acc, card = make_world()
        r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 100_00)
        iss.reverse(r.get("ADDITIONAL"))
        self.assertEqual(acc.held_minor, 0)
        self.assertEqual(acc.posted_minor, 1_000_00)


if __name__ == "__main__":
    unittest.main()
