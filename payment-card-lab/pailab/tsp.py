"""Token Service Provider.

Visa Token Service (VTS) y Mastercard Digital Enablement Service (MDES)
son los TSPs reales. Crean DPANs (Device Primary Account Numbers) que
reemplazan al PAN en el wallet del telefono.

Reglas clave que replicamos:
  * Un DPAN esta ligado a UN dispositivo + UN wallet provider.
  * El DPAN se puede apagar sin tocar la tarjeta fisica.
  * El comercio nunca ve el PAN real cuando se paga tokenizado.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from .crypto import HSM, random_key
from .lifecycle import CardStatus
from .luhn import generate_pan
from .models import Token


@dataclass
class TokenRecord:
    token: Token
    issuer_id: str
    pan_real: str
    requestor_id: str          # quien solicito (Apple, Google, Samsung)


class TSP:
    """Token Service Provider compartido entre emisores."""

    # BIN range que el TSP usa para emitir DPANs.
    DPAN_BIN = "999900"

    def __init__(self, name: str, hsm: HSM | None = None):
        self.name = name
        self.hsm = hsm or HSM()
        self._tokens: dict[str, TokenRecord] = {}   # dpan -> record
        self._by_pan: dict[str, list[str]] = {}      # pan -> list[dpan]

    def provision(self, *, issuer_id: str, pan_real: str, device_id: str,
                  wallet_provider: str) -> Token:
        """Emite un DPAN nuevo para (pan_real, device_id, wallet_provider).

        En produccion el TSP llama de vuelta al issuer (Token Authorization
        Request) para que el emisor confirme antes de emitir. Aqui asumimos
        que el caller ya valido el PAN/CVV.
        """
        dpan = generate_pan(self.DPAN_BIN)
        device_key = random_key()
        tok = Token(
            dpan=dpan,
            real_pan=pan_real,
            device_id=device_id,
            wallet_provider=wallet_provider,
            token_key=device_key,
            status=CardStatus.ACTIVE,
        )
        self._tokens[dpan] = TokenRecord(
            token=tok, issuer_id=issuer_id, pan_real=pan_real,
            requestor_id=wallet_provider,
        )
        self._by_pan.setdefault(pan_real, []).append(dpan)
        return tok

    def detokenize(self, dpan: str) -> str | None:
        """Solo el emisor puede llamar a esto. Devuelve PAN real."""
        rec = self._tokens.get(dpan)
        return rec.pan_real if rec else None

    def get_record(self, dpan: str) -> TokenRecord | None:
        return self._tokens.get(dpan)

    def suspend(self, dpan: str) -> bool:
        rec = self._tokens.get(dpan)
        if not rec:
            return False
        rec.token.status = CardStatus.BLOCKED
        return True

    def resume(self, dpan: str) -> bool:
        rec = self._tokens.get(dpan)
        if not rec:
            return False
        rec.token.status = CardStatus.ACTIVE
        return True

    def delete(self, dpan: str) -> bool:
        rec = self._tokens.pop(dpan, None)
        if not rec:
            return False
        self._by_pan.get(rec.pan_real, []).remove(dpan)
        return True

    def tokens_of(self, pan: str) -> list[Token]:
        return [self._tokens[d].token for d in self._by_pan.get(pan, [])]
