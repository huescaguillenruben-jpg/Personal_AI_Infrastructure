"""Codificador/decodificador minimo estilo ISO 8583.

ISO 8583 real es binario, con bitmap y BCD. Aqui lo representamos como
dict serializable a JSON: misma estructura logica, sin sufrimiento de bytes.
Cada DE (Data Element) se accede por su numero entero.

MTI (Message Type Indicator):
    0100/0110  Auth request / response
    0200/0210  Financial request / response (auth + capture)
    0400/0410  Reversal request / response
    0420       Reversal advice
    0500/0510  Reconciliation
    0800/0810  Network management
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


class MTI:
    AUTH_REQ = "0100"
    AUTH_RESP = "0110"
    FIN_REQ = "0200"
    FIN_RESP = "0210"
    REV_REQ = "0400"
    REV_RESP = "0410"
    REV_ADV = "0420"
    RECON_REQ = "0500"
    RECON_RESP = "0510"
    NETMGMT_REQ = "0800"
    NETMGMT_RESP = "0810"


# Mapa nombre legible -> numero de DE
DE = {
    "PAN": 2,
    "PROC_CODE": 3,
    "AMOUNT": 4,
    "DATETIME": 7,
    "STAN": 11,
    "EXPIRY": 14,
    "MCC": 18,
    "POS_ENTRY": 22,
    "ACQUIRER_ID": 32,
    "TRACK2": 35,
    "RRN": 37,
    "AUTH_CODE": 38,
    "RESPONSE_CODE": 39,
    "TERMINAL_ID": 41,
    "MERCHANT_ID": 42,
    "COUNTRY": 43,
    "ADDITIONAL": 48,
    "CURRENCY": 49,
    "PIN_BLOCK": 52,
    "ICC_DATA": 55,           # EMV: ARQC, ATC, UN, etc.
    "ORIGINAL_DATA": 90,
    "REPLACEMENT_AMTS": 95,
    "ECOM_DATA": 112,         # 3DS CAVV/ECI
    "TOKEN_DATA": 124,        # DPAN + cryptogram + nonce
}


@dataclass
class Iso8583Message:
    mti: str
    de: dict[int, str] = field(default_factory=dict)

    @classmethod
    def request(cls, mti: str) -> "Iso8583Message":
        m = cls(mti=mti)
        m.set("DATETIME", time.strftime("%m%d%H%M%S", time.gmtime()))
        return m

    def set(self, key: str | int, value) -> "Iso8583Message":
        num = DE[key] if isinstance(key, str) else int(key)
        self.de[num] = "" if value is None else str(value)
        return self

    def get(self, key: str | int, default=None):
        num = DE[key] if isinstance(key, str) else int(key)
        return self.de.get(num, default)

    # --- serializacion: real seria binario; aqui JSON -----------------
    def to_wire(self) -> bytes:
        return json.dumps({"mti": self.mti, "de": {str(k): v for k, v in self.de.items()}},
                          separators=(",", ":")).encode()

    @classmethod
    def from_wire(cls, raw: bytes) -> "Iso8583Message":
        obj = json.loads(raw.decode())
        return cls(mti=obj["mti"], de={int(k): v for k, v in obj["de"].items()})

    # --- helpers de respuesta ----------------------------------------
    def reply(self, rc: str, auth_code: str | None = None) -> "Iso8583Message":
        rsp_mti = {
            MTI.AUTH_REQ: MTI.AUTH_RESP,
            MTI.FIN_REQ: MTI.FIN_RESP,
            MTI.REV_REQ: MTI.REV_RESP,
            MTI.RECON_REQ: MTI.RECON_RESP,
            MTI.NETMGMT_REQ: MTI.NETMGMT_RESP,
        }.get(self.mti, "9999")
        r = Iso8583Message(mti=rsp_mti, de=dict(self.de))
        r.set("RESPONSE_CODE", rc)
        if auth_code:
            r.set("AUTH_CODE", auth_code)
        return r

    def __repr__(self) -> str:
        # Aplica masking al PAN si esta presente.
        from .logging_utils import mask_pan
        items = []
        for k in sorted(self.de):
            v = self.de[k]
            if k == DE["PAN"]:
                v = mask_pan(v)
            items.append(f"DE{k:03d}={v}")
        return f"<ISO8583 MTI={self.mti} {' '.join(items)}>"
