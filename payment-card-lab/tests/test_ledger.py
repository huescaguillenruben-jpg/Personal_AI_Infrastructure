import unittest

from pailab.ledger import InsufficientFundsError, Ledger
from pailab.models import Account, AccountType, Money


def chk_account() -> Account:
    return Account(account_id="acc1", holder_id="h1",
                   account_type=AccountType.CHECKING, currency="MXN")


def credit_account(limit_minor: int = 100_000_00) -> Account:
    return Account(account_id="acc2", holder_id="h1",
                   account_type=AccountType.CREDIT, currency="MXN",
                   credit_limit_minor=limit_minor)


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.l = Ledger()

    def test_open_deposit_hold_post(self):
        a = chk_account()
        self.l.open(a)
        self.l.deposit(a.account_id, Money(500_00), memo="ini")
        self.assertEqual(a.posted_minor, 500_00)
        self.assertEqual(a.available_minor(), 500_00)
        self.l.hold(a.account_id, Money(100_00), "txn1")
        self.assertEqual(a.held_minor, 100_00)
        self.assertEqual(a.available_minor(), 400_00)
        self.l.post(a.account_id, Money(100_00), Money(100_00), "txn1")
        self.assertEqual(a.posted_minor, 400_00)
        self.assertEqual(a.held_minor, 0)

    def test_release(self):
        a = chk_account()
        self.l.open(a)
        self.l.deposit(a.account_id, Money(500_00))
        self.l.hold(a.account_id, Money(100_00), "txn1")
        self.l.release(a.account_id, Money(100_00), "txn1")
        self.assertEqual(a.held_minor, 0)
        self.assertEqual(a.available_minor(), 500_00)

    def test_insufficient(self):
        a = chk_account()
        self.l.open(a)
        self.l.deposit(a.account_id, Money(50_00))
        with self.assertRaises(InsufficientFundsError):
            self.l.hold(a.account_id, Money(100_00), "txn1")

    def test_credit_account(self):
        a = credit_account(limit_minor=10_000_00)
        self.l.open(a)
        self.l.hold(a.account_id, Money(5_000_00), "txn1")
        self.l.post(a.account_id, Money(5_000_00), Money(5_000_00), "txn1")
        # En credito posted_minor crece con cada gasto.
        self.assertEqual(a.posted_minor, 5_000_00)
        self.assertEqual(a.available_minor(), 5_000_00)
        # No alcanza para otros 6000
        with self.assertRaises(InsufficientFundsError):
            self.l.hold(a.account_id, Money(6_000_00), "txn2")
        # Pago parcial
        self.l.deposit(a.account_id, Money(3_000_00), memo="pago")
        self.assertEqual(a.posted_minor, 2_000_00)
        self.assertEqual(a.available_minor(), 8_000_00)

    def test_journal(self):
        a = chk_account()
        self.l.open(a)
        self.l.deposit(a.account_id, Money(100_00))
        self.l.hold(a.account_id, Money(50_00), "t1")
        entries = list(self.l.entries(a.account_id))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].op, "deposit")
        self.assertEqual(entries[1].op, "hold")


if __name__ == "__main__":
    unittest.main()
