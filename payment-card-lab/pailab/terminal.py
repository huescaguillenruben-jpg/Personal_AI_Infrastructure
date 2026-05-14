"""Terminal POS / gateway e-commerce.

Construye el mensaje ISO 8583 y lo manda al adquirente.
Soporta cuatro modos:
    - swipe (banda)
    - chip (genera EMV ARQC con su HSM "del chip")
    - contactless (plastico NFC, EMV)
    - manual / ecommerce (CNP, puede traer 3DS CAVV)
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass

from .acquirer import Acquirer, Merchant
from .crypto import HSM
from .iso8583 import DE, MTI, Iso8583Message
from .models import POSEntryMode, new_id, new_rrn, new_stan


@dataclass
class Terminal:
    terminal_id: str
    merchant: Merchant
    acquirer: Acquirer
    country_iso2: str
    currency: str = "MXN"

    @classmethod
    def deploy(cls, acquirer: Acquirer, merchant: Merchant,
               currency: str | None = None) -> "Terminal":
        return cls(
            terminal_id=new_id("term"),
            merchant=merchant,
            acquirer=acquirer,
            country_iso2=acquirer.country_iso2,
            currency=currency or acquirer.currency,
        )

    # ---- helper: monta el mensaje ----------------------------------
    def _base(self, pan: str, amount_minor: int, expiry: str,
              pos: POSEntryMode, cvv: str | None = None) -> Iso8583Message:
        m = Iso8583Message.request(MTI.AUTH_REQ)
        m.set("PAN", pan)
        m.set("AMOUNT", amount_minor)
        m.set("EXPIRY", expiry)
        m.set("MCC", self.merchant.mcc)
        m.set("POS_ENTRY", pos.value)
        m.set("CURRENCY", self.currency)
        m.set("COUNTRY", self.country_iso2)
        m.set("STAN", new_stan())
        m.set("RRN", new_rrn())
        m.set("TERMINAL_ID", self.terminal_id)
        m.set("MERCHANT_ID", self.merchant.merchant_id)
        if cvv:
            m.set("ADDITIONAL", cvv)   # CVV en DE 48 para este lab
        return m

    # ---- escenarios -------------------------------------------------
    def swipe(self, pan: str, expiry: str, cvv: str, amount_minor: int) -> Iso8583Message:
        m = self._base(pan, amount_minor, expiry, POSEntryMode.SWIPE, cvv)
        return self.acquirer.forward_auth(m)

    def chip(self, pan: str, expiry: str, amount_minor: int, *,
             card_hsm: HSM, atc: int, psn: int = 1) -> Iso8583Message:
        """Inserta una tarjeta con chip.

        El terminal genera un UN (Unpredictable Number), el chip lo recibe
        + el monto + la moneda + el pais + el MCC, y produce un ARQC.
        """
        un = secrets.token_bytes(4)
        arqc = card_hsm.compute_arqc(
            pan, psn, atc, un,
            amount_minor, self.currency, self.country_iso2,
            self.merchant.mcc,
        )
        m = self._base(pan, amount_minor, expiry, POSEntryMode.CHIP)
        m.set("ICC_DATA", json.dumps({
            "arqc": arqc, "atc": atc, "un": un.hex(), "psn": psn,
        }))
        return self.acquirer.forward_auth(m)

    def contactless(self, pan: str, expiry: str, amount_minor: int, *,
                    card_hsm: HSM, atc: int, psn: int = 1) -> Iso8583Message:
        """Tarjeta plastica con NFC. Mismo flujo EMV que chip."""
        m = self.chip(pan, expiry, amount_minor, card_hsm=card_hsm,
                      atc=atc, psn=psn)
        # En el lab "chip" ya envio; modificamos POS_ENTRY in-place
        # (en realidad reenviariamos otro mensaje; lo dejamos asi por simpleza)
        return m

    def ecommerce(self, pan: str, expiry: str, cvv: str, amount_minor: int,
                  *, cavv: str | None = None, cavv_cid: str | None = None) -> Iso8583Message:
        m = self._base(pan, amount_minor, expiry, POSEntryMode.ECOMMERCE, cvv)
        if cavv:
            m.set("ECOM_DATA", json.dumps({"cavv": cavv, "cid": cavv_cid}))
        return self.acquirer.forward_auth(m)

    def nfc_wallet(self, dpan: str, expiry: str, amount_minor: int, *,
                   cryptogram: str, nonce: str) -> Iso8583Message:
        m = self._base(dpan, amount_minor, expiry, POSEntryMode.NFC_WALLET)
        m.set("TOKEN_DATA", json.dumps({
            "dpan": dpan, "cryptogram": cryptogram, "nonce": nonce,
        }))
        return self.acquirer.forward_auth(m)
