"""Motor de reglas de fraude del emisor.

En un banco real esto es un modelo de ML + sistema de reglas + reglas
del usuario (limites configurables) + listas globales. Aqui replicamos
el esqueleto: cada regla evalua un AuthRequest y suma puntos. Si supera
un umbral, el emisor exige 3DS o rechaza.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .models import AuthRequest, POSEntryMode


# MCCs de alto riesgo (subset ilustrativo).
HIGH_RISK_MCC = {
    "6051",   # quasi-cash / monedas extranjeras
    "7995",   # apuestas
    "5967",   # adult content
    "4829",   # wire transfer / money orders
}


@dataclass
class FraudDecision:
    score: int                   # 0-100
    require_3ds: bool
    decline: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class VelocityWindow:
    pan: str
    timestamps: deque[float] = field(default_factory=deque)
    amounts: deque[int] = field(default_factory=deque)


class FraudEngine:
    """Reglas configurables. Aplica scoring acumulativo."""

    def __init__(
        self,
        velocity_window_sec: int = 60,
        velocity_max_txn: int = 5,
        daily_amount_limit_minor: int = 50_000_00,
        cnp_3ds_amount_minor: int = 1_500_00,
        decline_threshold: int = 80,
        challenge_threshold: int = 40,
    ):
        self.velocity_window_sec = velocity_window_sec
        self.velocity_max_txn = velocity_max_txn
        self.daily_amount_limit_minor = daily_amount_limit_minor
        self.cnp_3ds_amount_minor = cnp_3ds_amount_minor
        self.decline_threshold = decline_threshold
        self.challenge_threshold = challenge_threshold
        # Estado por PAN (en realidad seria por cuenta + canal en un banco)
        self._velocity: dict[str, VelocityWindow] = {}
        self._daily: dict[str, tuple[float, int]] = {}    # pan -> (day_start, sum)
        self._declines: dict[str, int] = {}               # pan -> count
        self._declared_country: dict[str, str] = {}        # pan -> country
        self._blocked_pan: set[str] = set()

    # --- API publica ------------------------------------------------------
    def declare_home_country(self, pan: str, country_iso2: str) -> None:
        self._declared_country[pan] = country_iso2

    def block_pan(self, pan: str) -> None:
        self._blocked_pan.add(pan)

    def record_decline(self, pan: str) -> None:
        self._declines[pan] = self._declines.get(pan, 0) + 1
        if self._declines[pan] >= 5:
            self.block_pan(pan)

    def reset_declines(self, pan: str) -> None:
        self._declines.pop(pan, None)

    def evaluate(self, req: AuthRequest) -> FraudDecision:
        d = FraudDecision(score=0, require_3ds=False, decline=False)

        if req.pan in self._blocked_pan:
            d.score = 100
            d.decline = True
            d.reasons.append("PAN bloqueado por sistema antifraude")
            return d

        now = time.time()

        # Regla 1: velocidad
        vw = self._velocity.setdefault(req.pan, VelocityWindow(pan=req.pan))
        while vw.timestamps and now - vw.timestamps[0] > self.velocity_window_sec:
            vw.timestamps.popleft()
            vw.amounts.popleft()
        if len(vw.timestamps) >= self.velocity_max_txn:
            d.score += 40
            d.reasons.append(
                f"velocidad: {len(vw.timestamps)} txn en {self.velocity_window_sec}s")

        # Regla 2: limite diario
        day_start = int(now // 86400) * 86400
        prev_day, prev_sum = self._daily.get(req.pan, (day_start, 0))
        if prev_day != day_start:
            prev_sum = 0
        new_sum = prev_sum + req.amount.amount_minor
        if new_sum > self.daily_amount_limit_minor:
            d.score += 50
            d.reasons.append("excede limite diario")

        # Regla 3: MCC de alto riesgo
        if req.mcc in HIGH_RISK_MCC:
            d.score += 20
            d.reasons.append(f"MCC riesgoso {req.mcc}")

        # Regla 4: geo mismatch
        home = self._declared_country.get(req.pan)
        if home and req.country_iso2 != home:
            d.score += 25
            d.reasons.append(f"pais {req.country_iso2} != home {home}")

        # Regla 5: e-commerce CNP de monto alto -> exigir 3DS
        if req.pos_entry in (POSEntryMode.ECOMMERCE, POSEntryMode.MANUAL):
            if req.amount.amount_minor >= self.cnp_3ds_amount_minor and not req.cavv:
                d.require_3ds = True
                d.reasons.append("CNP monto alto sin 3DS")

        # Decision final
        if d.score >= self.decline_threshold:
            d.decline = True
        elif d.score >= self.challenge_threshold:
            # SCA (3DS) solo tiene sentido en card-not-present.
            # En card-present, un score elevado se traduce a decline directo.
            if req.pos_entry in (POSEntryMode.ECOMMERCE, POSEntryMode.MANUAL):
                d.require_3ds = True
            else:
                d.decline = True

        return d

    def record_approved(self, req: AuthRequest) -> None:
        """Llamar tras aprobar. Actualiza ventanas."""
        now = time.time()
        vw = self._velocity.setdefault(req.pan, VelocityWindow(pan=req.pan))
        vw.timestamps.append(now)
        vw.amounts.append(req.amount.amount_minor)
        day_start = int(now // 86400) * 86400
        prev_day, prev_sum = self._daily.get(req.pan, (day_start, 0))
        if prev_day != day_start:
            prev_sum = 0
        self._daily[req.pan] = (day_start, prev_sum + req.amount.amount_minor)
