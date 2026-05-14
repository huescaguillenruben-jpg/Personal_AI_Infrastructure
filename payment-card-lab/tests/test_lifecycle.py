import unittest

from pailab.lifecycle import CardStatus, can_transition, is_usable


class TestLifecycle(unittest.TestCase):
    def test_valid_transitions(self):
        self.assertTrue(can_transition(CardStatus.ISSUED, CardStatus.ACTIVE))
        self.assertTrue(can_transition(CardStatus.ACTIVE, CardStatus.BLOCKED))
        self.assertTrue(can_transition(CardStatus.BLOCKED, CardStatus.ACTIVE))
        self.assertTrue(can_transition(CardStatus.ACTIVE, CardStatus.STOLEN))

    def test_invalid_transitions(self):
        self.assertFalse(can_transition(CardStatus.CLOSED, CardStatus.ACTIVE))
        self.assertFalse(can_transition(CardStatus.STOLEN, CardStatus.ACTIVE))
        self.assertFalse(can_transition(CardStatus.LOST, CardStatus.ACTIVE))

    def test_only_active_is_usable(self):
        self.assertTrue(is_usable(CardStatus.ACTIVE))
        for s in [CardStatus.ISSUED, CardStatus.BLOCKED, CardStatus.LOST,
                  CardStatus.STOLEN, CardStatus.EXPIRED, CardStatus.CLOSED]:
            self.assertFalse(is_usable(s))


if __name__ == "__main__":
    unittest.main()
