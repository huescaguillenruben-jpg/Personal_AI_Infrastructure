import unittest

from pailab.clearing import ClearingEngine
from pailab.luhn import bin_of

from tests._world import make_world


class TestClearing(unittest.TestCase):
    def test_batch_settle(self):
        iss, acq, term, _, acc, card = make_world(deposit_minor=10_000_00)
        for amount in (50_00, 75_00, 30_00):
            r = term.swipe(card.pan, card.expiry_mmYY, card.cvv, amount)
            self.assertEqual(r.get("RESPONSE_CODE"), "00")
        self.assertEqual(acc.held_minor, 155_00)
        ce = ClearingEngine(acq, {bin_of(card.pan): iss})
        result = ce.run_batch()
        self.assertEqual(result["captured_now"], 3)
        self.assertEqual(result["settled"], 3)
        self.assertEqual(acc.held_minor, 0)
        self.assertEqual(acc.posted_minor, 9_845_00)
        merchant = next(iter(acq.merchants.values()))
        self.assertEqual(merchant.payable_minor, 155_00)


if __name__ == "__main__":
    unittest.main()
