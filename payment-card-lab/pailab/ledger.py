"""Libro mayor simplificado para la contabilidad del emisor.

Toda transaccion produce asientos. En lugar de doble partida estricta
(que requeriria una contracuenta por cada movimiento), llevamos por
cuenta dos saldos: `posted` (firme) y `held` (autorizado, no cobrado).

Esto refleja lo que tu app del banco te muestra: "Saldo disponible" vs.
"Saldo en linea" vs. "Saldo congelado".

Toda operacion es atomica y deja huella en un journal append-only.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Iterator

from .models import Account, AccountType, Money


@dataclass
class JournalEntry:
    ts: float
    account_id: str
    op: str                   # hold, release, post, refund, deposit, withdraw
    amount_minor: int
    currency: str
    txn_id: str | None
    memo: str = ""


class InsufficientFundsError(Exception):
    pass


class Ledger:
    """Maneja cuentas y journal. Thread-safe."""

    def __init__(self):
        self._lock = threading.RLock()
        self.accounts: dict[str, Account] = {}
        self.journal: list[JournalEntry] = []

    # --- gestion de cuentas ------------------------------------------------
    def open(self, account: Account) -> None:
        with self._lock:
            if account.account_id in self.accounts:
                raise ValueError("Cuenta ya existe")
            self.accounts[account.account_id] = account

    def get(self, account_id: str) -> Account:
        with self._lock:
            return self.accounts[account_id]

    # --- operaciones de saldo ---------------------------------------------
    def deposit(self, account_id: str, amount: Money, memo: str = "") -> None:
        with self._lock:
            acc = self.accounts[account_id]
            assert acc.currency == amount.currency
            if acc.account_type == AccountType.CHECKING:
                acc.posted_minor += amount.amount_minor
            else:
                # En credito, depositar = pagar la tarjeta = reducir deuda
                acc.posted_minor -= amount.amount_minor
            self._log("deposit", account_id, amount, None, memo)

    def hold(self, account_id: str, amount: Money, txn_id: str,
             memo: str = "") -> None:
        with self._lock:
            acc = self.accounts[account_id]
            if acc.closed:
                raise InsufficientFundsError("Cuenta cerrada")
            if amount.amount_minor > acc.available_minor():
                raise InsufficientFundsError(
                    f"available={acc.available_minor()} need={amount.amount_minor}")
            acc.held_minor += amount.amount_minor
            self._log("hold", account_id, amount, txn_id, memo)

    def release(self, account_id: str, amount: Money, txn_id: str,
                memo: str = "") -> None:
        """Libera un hold sin posting (reverso de autorizacion)."""
        with self._lock:
            acc = self.accounts[account_id]
            acc.held_minor = max(0, acc.held_minor - amount.amount_minor)
            self._log("release", account_id, amount, txn_id, memo)

    def post(self, account_id: str, hold_amount: Money,
             captured_amount: Money, txn_id: str, memo: str = "") -> None:
        """Captura: libera el hold y mueve el capturado a posted."""
        assert hold_amount.currency == captured_amount.currency
        with self._lock:
            acc = self.accounts[account_id]
            acc.held_minor = max(0, acc.held_minor - hold_amount.amount_minor)
            if acc.account_type == AccountType.CHECKING:
                acc.posted_minor -= captured_amount.amount_minor
            else:
                acc.posted_minor += captured_amount.amount_minor
            self._log("post", account_id, captured_amount, txn_id, memo)

    def refund(self, account_id: str, amount: Money, txn_id: str,
               memo: str = "") -> None:
        with self._lock:
            acc = self.accounts[account_id]
            if acc.account_type == AccountType.CHECKING:
                acc.posted_minor += amount.amount_minor
            else:
                acc.posted_minor -= amount.amount_minor
            self._log("refund", account_id, amount, txn_id, memo)

    # --- journal ----------------------------------------------------------
    def _log(self, op: str, account_id: str, amount: Money,
             txn_id: str | None, memo: str) -> None:
        self.journal.append(JournalEntry(
            ts=time.time(),
            account_id=account_id,
            op=op,
            amount_minor=amount.amount_minor,
            currency=amount.currency,
            txn_id=txn_id,
            memo=memo,
        ))

    def entries(self, account_id: str | None = None) -> Iterator[JournalEntry]:
        for e in self.journal:
            if account_id is None or e.account_id == account_id:
                yield e
