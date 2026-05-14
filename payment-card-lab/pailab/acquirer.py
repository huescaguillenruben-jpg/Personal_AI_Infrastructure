"""Acquirer (banco adquirente del comercio).

Recibe transacciones desde los terminales de sus comercios, las firma
con su BIN y las pasa a la red de marca para enrutar al emisor.

En produccion el adquirente:
  * Mantiene cuentas de comercio (MID)
  * Cobra fees (interchange, scheme, markup)
  * Liquida fondos al comercio en T+N

Aqui modelamos: registro de auth aprobadas, batch de clearing, y la
liquidacion al comercio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .iso8583 import DE, MTI, Iso8583Message
from .logging_utils import get_logger
from .models import Transaction, TxnState, new_id


log = get_logger("acquirer")


@dataclass
class Merchant:
    merchant_id: str
    name: str
    mcc: str
    country_iso2: str
    payable_minor: int = 0   # lo que el adquirente le debe al comercio


@dataclass
class PendingAuth:
    txn_id: str
    merchant_id: str
    pan_first6: str
    amount_minor: int
    currency: str


class Acquirer:
    def __init__(self, name: str, country_iso2: str = "MX",
                 currency: str = "MXN"):
        self.name = name
        self.acquirer_id = new_id("acq")
        self.country_iso2 = country_iso2
        self.currency = currency
        self.merchants: dict[str, Merchant] = {}
        self.pending_auths: list[PendingAuth] = []      # aprobadas, no capturadas
        self.captured: list[PendingAuth] = []           # ya capturadas, esperan settle
        self.settled_count: int = 0
        self.network = None                              # se setea afuera

    def onboard_merchant(self, name: str, mcc: str) -> Merchant:
        m = Merchant(
            merchant_id=new_id("mid"),
            name=name, mcc=mcc, country_iso2=self.country_iso2,
        )
        self.merchants[m.merchant_id] = m
        return m

    def forward_auth(self, msg: Iso8583Message) -> Iso8583Message:
        """Inserta acquirer_id, reenvia a la red y trackea respuesta."""
        msg.set("ACQUIRER_ID", self.acquirer_id)
        rsp = self.network.route(msg)
        if rsp.get("RESPONSE_CODE") == "00":
            txn_id = rsp.get("ADDITIONAL") or ""
            self.pending_auths.append(PendingAuth(
                txn_id=txn_id,
                merchant_id=msg.get("MERCHANT_ID", ""),
                pan_first6=(msg.get("PAN", "") or "")[:6],
                amount_minor=int(msg.get("AMOUNT", "0") or "0"),
                currency=msg.get("CURRENCY", self.currency),
            ))
        return rsp

    def mark_captured(self, txn_id: str) -> None:
        for p in list(self.pending_auths):
            if p.txn_id == txn_id:
                self.pending_auths.remove(p)
                self.captured.append(p)
                return

    def settle_batch(self) -> int:
        """Liquida lo capturado: aumenta payable del comercio."""
        n = 0
        for p in self.captured:
            m = self.merchants.get(p.merchant_id)
            if m:
                m.payable_minor += p.amount_minor
            n += 1
        self.captured.clear()
        self.settled_count += n
        log.info("Acquirer %s settled %d txns", self.name, n)
        return n
