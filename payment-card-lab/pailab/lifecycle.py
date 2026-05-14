"""Maquina de estados del ciclo de vida de una tarjeta."""

from __future__ import annotations

from enum import Enum


class CardStatus(str, Enum):
    REQUESTED = "requested"      # impresa pero no entregada
    ISSUED = "issued"            # entregada, no activada
    ACTIVE = "active"            # operando normal
    BLOCKED = "blocked"          # bloqueo temporal (PIN, sospecha de fraude)
    LOST = "lost"
    STOLEN = "stolen"
    EXPIRED = "expired"
    CLOSED = "closed"


# Transiciones permitidas (from -> set(to))
_TRANSITIONS: dict[CardStatus, set[CardStatus]] = {
    CardStatus.REQUESTED: {CardStatus.ISSUED, CardStatus.CLOSED},
    CardStatus.ISSUED: {CardStatus.ACTIVE, CardStatus.LOST, CardStatus.STOLEN, CardStatus.CLOSED},
    CardStatus.ACTIVE: {CardStatus.BLOCKED, CardStatus.LOST, CardStatus.STOLEN,
                        CardStatus.EXPIRED, CardStatus.CLOSED},
    CardStatus.BLOCKED: {CardStatus.ACTIVE, CardStatus.CLOSED, CardStatus.STOLEN, CardStatus.LOST},
    CardStatus.LOST: {CardStatus.CLOSED},
    CardStatus.STOLEN: {CardStatus.CLOSED},
    CardStatus.EXPIRED: {CardStatus.CLOSED},
    CardStatus.CLOSED: set(),
}


def can_transition(src: CardStatus, dst: CardStatus) -> bool:
    return dst in _TRANSITIONS.get(src, set())


def is_usable(status: CardStatus) -> bool:
    """Solo ACTIVE permite autorizaciones."""
    return status == CardStatus.ACTIVE
