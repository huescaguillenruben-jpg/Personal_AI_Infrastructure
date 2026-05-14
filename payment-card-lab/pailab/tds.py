"""3-D Secure (3DS / EMV 3DS) simulado.

Flujo real (resumido):
    1. Comercio detecta CNP. Manda al ACS (Access Control Server) del emisor
       una request via DS (Directory Server).
    2. ACS aplica risk-based authentication:
         - frictionless: aprueba sin pedirle nada al usuario
         - challenge: pide OTP, biometria, app push
    3. Si pasa, ACS firma un CAVV (Cardholder Auth Verification Value)
       y un ECI (E-Commerce Indicator).
    4. El comercio adjunta CAVV+ECI a la auth ISO 8583.

Aqui resumimos: el ACS guarda challenges abiertos, valida OTPs y
genera CAVVs ligados a (PAN, monto, txn_id).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from .crypto import const_time_eq, random_key


@dataclass
class ThreeDSChallenge:
    challenge_id: str
    pan: str
    amount_minor: int
    expected_otp: str
    created_ts: float
    consumed: bool = False


@dataclass
class ThreeDSResult:
    success: bool
    cavv: str | None
    eci: str | None      # "05"=auth ok, "07"=attempt
    reason: str = ""


class ACS:
    """Access Control Server del emisor."""

    OTP_TTL_SEC = 180

    def __init__(self):
        self._key = random_key()
        self._challenges: dict[str, ThreeDSChallenge] = {}

    # Servicio para "enrolarse" — en este lab cualquier PAN del emisor pasa.
    def is_enrolled(self, pan: str) -> bool:
        return True

    def initiate(self, pan: str, amount_minor: int) -> tuple[str, str]:
        """Crea un challenge. Devuelve (challenge_id, otp simulada).

        En la vida real el OTP se envia por SMS / app / email; nadie lo
        ve en una respuesta API. Aqui lo retornamos para que el demo
        pueda completar el flujo automaticamente.
        """
        cid = f"3ds_{secrets.token_hex(8)}"
        otp = f"{secrets.randbelow(1_000_000):06d}"
        self._challenges[cid] = ThreeDSChallenge(
            challenge_id=cid,
            pan=pan,
            amount_minor=amount_minor,
            expected_otp=otp,
            created_ts=time.time(),
        )
        return cid, otp

    def verify(self, challenge_id: str, otp: str) -> ThreeDSResult:
        ch = self._challenges.get(challenge_id)
        if not ch:
            return ThreeDSResult(False, None, None, "challenge inexistente")
        if ch.consumed:
            return ThreeDSResult(False, None, None, "challenge ya usado")
        if time.time() - ch.created_ts > self.OTP_TTL_SEC:
            return ThreeDSResult(False, None, None, "OTP expirada")
        if not const_time_eq(ch.expected_otp, otp):
            return ThreeDSResult(False, None, None, "OTP incorrecta")
        ch.consumed = True
        cavv = hmac.new(
            self._key,
            f"{ch.pan}|{ch.amount_minor}|{ch.challenge_id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:40]
        return ThreeDSResult(True, cavv, "05")

    def verify_cavv(self, cavv: str, pan: str, amount_minor: int,
                    challenge_id: str) -> bool:
        expected = hmac.new(
            self._key,
            f"{pan}|{amount_minor}|{challenge_id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:40]
        return const_time_eq(expected, cavv)
