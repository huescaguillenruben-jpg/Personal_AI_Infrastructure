"""Wallet movil con Secure Element (SE/TEE) simulado.

En un telefono real:
  * iOS: el Secure Enclave guarda las llaves; Wallet.app habla con el SE
  * Android: el TEE (Trusted Execution Environment) o un HSM Titan/StrongBox
  * Samsung: Knox Vault

La llave del token NUNCA sale del SE. Cada pago la usa el SE para firmar
un criptograma, devuelve el criptograma firmado, y el resto del telefono
solo ve resultados — nunca la llave.

Aqui simulamos el SE como un objeto interno cuyo contenido marcamos como
"privado": el resto del codigo solo lo accede via tap_to_pay().
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Optional

from .crypto import HSM
from .iso8583 import Iso8583Message
from .logging_utils import get_logger, mask_pan
from .models import Token


log = get_logger("wallet")


class _SecureElement:
    """Guarda llaves de tokens. NO expone bytes hacia afuera."""

    def __init__(self):
        self._items: dict[str, dict] = {}   # dpan -> {key, expiry, issuer}

    def store(self, dpan: str, key: bytes, expiry: str, issuer) -> None:
        self._items[dpan] = {"key": key, "expiry": expiry, "issuer": issuer}

    def has(self, dpan: str) -> bool:
        return dpan in self._items

    def sign(self, hsm: HSM, dpan: str, amount_minor: int, nonce: str) -> str:
        """Unico metodo que toca la llave. Devuelve criptograma firmado."""
        if dpan not in self._items:
            raise KeyError("DPAN no provisionado en este SE")
        key = self._items[dpan]["key"]
        return hsm.compute_token_cryptogram(key, dpan, amount_minor, nonce)

    def expiry(self, dpan: str) -> str:
        return self._items[dpan]["expiry"]

    def issuer(self, dpan: str, *, _):
        # Solo lectura, evita exposicion fuera del SE.
        return self._items[dpan]["issuer"]

    def remove(self, dpan: str) -> None:
        self._items.pop(dpan, None)

    def list_dpans(self) -> list[str]:
        return list(self._items)


@dataclass
class MobileWallet:
    device_id: str
    provider: str                # apple_pay, google_pay, samsung_pay
    _se: _SecureElement = field(default_factory=_SecureElement)
    _hsm: HSM = field(default_factory=HSM)

    @classmethod
    def new(cls, provider: str = "apple_pay") -> "MobileWallet":
        return cls(device_id=f"device_{secrets.token_hex(4)}", provider=provider)

    def add_card(self, *, issuer, pan: str, expiry: str, cvv: str) -> str:
        """Aprovisiona: pide al issuer un DPAN.

        En la vida real esto implica una autenticacion adicional (3DS,
        biometria, OTP) y un Token Authorization Request del TSP al
        emisor. Lo simplificamos.
        """
        tok: Token = issuer.provision_token(
            pan=pan, expiry_mmYY=expiry, cvv=cvv,
            device_id=self.device_id, wallet_provider=self.provider,
        )
        self._se.store(tok.dpan, tok.token_key, tok.expiry_mmYY if hasattr(tok, "expiry_mmYY") else expiry, issuer)
        # Tras provisionar, las llaves de la tarjeta fisica salen del wallet
        # (no las guardamos nunca: solo el DPAN y su llave).
        log.info("Provisionado dpan=%s device=%s provider=%s",
                 mask_pan(tok.dpan), self.device_id, self.provider)
        return tok.dpan

    def remove_card(self, dpan: str, issuer) -> None:
        self._se.remove(dpan)
        issuer.tsp.delete(dpan)

    def list_dpans(self) -> list[str]:
        return self._se.list_dpans()

    def tap_to_pay(self, *, dpan: str, terminal, amount_minor: int,
                   expiry_hint: str | None = None) -> Iso8583Message:
        """Genera nonce, firma criptograma con el SE, lo manda al terminal."""
        nonce = secrets.token_hex(8)
        cryptogram = self._se.sign(self._hsm, dpan, amount_minor, nonce)
        # En NFC real el expiry del DPAN se manda en el track equivalente.
        expiry = expiry_hint or self._se.expiry(dpan)
        return terminal.nfc_wallet(
            dpan=dpan, expiry=expiry, amount_minor=amount_minor,
            cryptogram=cryptogram, nonce=nonce,
        )
