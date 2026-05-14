"""Red de marca (Visa, Mastercard, Amex...).

Rol: enrutar mensajes ISO 8583 desde el adquirente hacia el emisor
correcto segun el BIN del PAN.
"""

from __future__ import annotations

from .iso8583 import DE, Iso8583Message
from .logging_utils import get_logger
from .luhn import bin_of


log = get_logger("network")


class CardNetwork:
    def __init__(self, name: str):
        self.name = name
        self._issuers_by_bin: dict[str, object] = {}   # bin -> Issuer
        self._tsps: list = []                            # TSPs registrados

    def register_issuer(self, bin_prefix: str, issuer) -> None:
        self._issuers_by_bin[bin_prefix] = issuer

    def register_tsp(self, tsp) -> None:
        """Registra un TSP para que la red pueda detokenizar DPANs."""
        if tsp not in self._tsps:
            self._tsps.append(tsp)

    def _resolve_issuer(self, pan: str):
        # Match directo por BIN del PAN.
        issuer = self._issuers_by_bin.get(bin_of(pan))
        if issuer:
            return issuer
        # Si el BIN es de un TSP, resolver al PAN real y reintentar.
        for tsp in self._tsps:
            real = tsp.detokenize(pan)
            if real:
                return self._issuers_by_bin.get(bin_of(real))
        return None

    def route(self, msg: Iso8583Message) -> Iso8583Message:
        """Encuentra emisor por BIN y delega la autorizacion."""
        from .errors import RC
        pan = msg.get("PAN", "")
        issuer = self._resolve_issuer(pan)
        if not issuer:
            # No conocemos al emisor.
            return msg.reply(RC.NO_ISSUER.value)
        # Construir AuthRequest desde el ISO 8583.
        from .models import AuthRequest, Money, POSEntryMode
        amount = Money(int(msg.get("AMOUNT", "0")), msg.get("CURRENCY", "MXN"))
        pos = POSEntryMode(msg.get("POS_ENTRY", "manual"))
        emv = None
        if msg.get("ICC_DATA"):
            import json as _json
            emv = _json.loads(msg.get("ICC_DATA"))
        token_data = None
        if msg.get("TOKEN_DATA"):
            import json as _json
            token_data = _json.loads(msg.get("TOKEN_DATA"))
        cavv = None
        cavv_cid = None
        if msg.get("ECOM_DATA"):
            import json as _json
            ecom = _json.loads(msg.get("ECOM_DATA"))
            cavv = ecom.get("cavv")
            cavv_cid = ecom.get("cid")
        req = AuthRequest(
            pan=pan,
            expiry_mmYY=msg.get("EXPIRY", ""),
            cvv=msg.get("ADDITIONAL"),    # mapeamos CVV via DE 48 en este lab
            amount=amount,
            mcc=msg.get("MCC", "0000"),
            merchant_id=msg.get("MERCHANT_ID", ""),
            terminal_id=msg.get("TERMINAL_ID", ""),
            pos_entry=pos,
            country_iso2=msg.get("COUNTRY", "MX"),
            emv=emv if emv else {"cavv_cid": cavv_cid} if cavv_cid else None,
            cavv=cavv,
            cryptogram=token_data.get("cryptogram") if token_data else None,
            nonce=token_data.get("nonce") if token_data else None,
            dpan=token_data.get("dpan") if token_data else None,
            stan=int(msg.get("STAN", "0") or "0"),
            rrn=msg.get("RRN", ""),
        )
        if emv and cavv_cid:
            req.emv = {**emv, "cavv_cid": cavv_cid}
        outcome = issuer.authorize(req)
        rsp = msg.reply(outcome.rc.value, auth_code=outcome.txn.auth_code if outcome.txn else None)
        if outcome.threeds_challenge:
            cid, otp = outcome.threeds_challenge
            import json as _json
            rsp.set("ECOM_DATA", _json.dumps({"challenge_id": cid, "otp_demo": otp}))
        # Attach txn_id for downstream capture
        if outcome.txn:
            rsp.set("ADDITIONAL", outcome.txn.txn_id)
        return rsp
