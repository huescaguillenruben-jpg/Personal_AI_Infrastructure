import unittest

from pailab.errors import RC
from pailab.wallet import MobileWallet

from tests._world import make_world


class TestWallet(unittest.TestCase):
    def test_provision_and_tap(self):
        iss, acq, term, _, acc, card = make_world()
        phone = MobileWallet.new("apple_pay")
        dpan = phone.add_card(issuer=iss, pan=card.pan,
                              expiry=card.expiry_mmYY, cvv=card.cvv)
        self.assertNotEqual(dpan, card.pan)
        self.assertTrue(phone.list_dpans() == [dpan])

        r = phone.tap_to_pay(dpan=dpan, terminal=term, amount_minor=200_00,
                             expiry_hint=card.expiry_mmYY)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.APPROVED.value)
        self.assertEqual(acc.held_minor, 200_00)

    def test_bad_cryptogram_rejected(self):
        iss, acq, term, _, _, card = make_world()
        phone = MobileWallet.new("apple_pay")
        dpan = phone.add_card(issuer=iss, pan=card.pan,
                              expiry=card.expiry_mmYY, cvv=card.cvv)
        # Bypass del SE: pasar cryptogram inventado directo al terminal
        r = term.nfc_wallet(dpan=dpan, expiry=card.expiry_mmYY,
                            amount_minor=100_00,
                            cryptogram="deadbeef" * 4, nonce="abc")
        self.assertEqual(r.get("RESPONSE_CODE"), RC.CRYPTO_FAILURE.value)

    def test_suspended_dpan(self):
        iss, acq, term, _, _, card = make_world()
        phone = MobileWallet.new("google_pay")
        dpan = phone.add_card(issuer=iss, pan=card.pan,
                              expiry=card.expiry_mmYY, cvv=card.cvv)
        iss.tsp.suspend(dpan)
        r = phone.tap_to_pay(dpan=dpan, terminal=term, amount_minor=10_00,
                             expiry_hint=card.expiry_mmYY)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.RESTRICTED_CARD.value)

    def test_stolen_card_disables_all_dpans(self):
        from pailab.lifecycle import CardStatus
        iss, acq, term, _, _, card = make_world()
        phone = MobileWallet.new("samsung_pay")
        dpan = phone.add_card(issuer=iss, pan=card.pan,
                              expiry=card.expiry_mmYY, cvv=card.cvv)
        iss.set_card_status(card.pan, CardStatus.STOLEN)
        r = phone.tap_to_pay(dpan=dpan, terminal=term, amount_minor=10_00,
                             expiry_hint=card.expiry_mmYY)
        self.assertEqual(r.get("RESPONSE_CODE"), RC.RESTRICTED_CARD.value)


if __name__ == "__main__":
    unittest.main()
