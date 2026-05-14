"""Algoritmo de Luhn (ISO/IEC 7812) y generacion de PANs sinteticos.

El Luhn es solo un checksum: detecta errores de tipeo, no autentica nada.
Cualquier numero generado aqui es sintetico y no existe en ningun banco real.
"""

from __future__ import annotations

import secrets


def luhn_checksum_of_partial(partial: str) -> int:
    """Calcula el digito de control que se le agregaria a `partial`."""
    if not partial.isdigit():
        raise ValueError("Solo digitos")
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def luhn_valid(pan: str) -> bool:
    """True si `pan` pasa la verificacion de Luhn."""
    if not pan or not pan.isdigit() or len(pan) < 12:
        return False
    return luhn_checksum_of_partial(pan[:-1]) == int(pan[-1])


def generate_pan(bin_prefix: str, length: int = 16) -> str:
    """Genera un PAN sintetico para este lab.

    `bin_prefix` es un BIN ficticio (6-8 digitos). El resto se llena con
    digitos aleatorios y se cierra con el digito de Luhn.
    """
    if not bin_prefix.isdigit() or not (4 <= len(bin_prefix) <= 8):
        raise ValueError("BIN debe ser 4-8 digitos numericos")
    if length < len(bin_prefix) + 2:
        raise ValueError("length demasiado corto")
    body_len = length - len(bin_prefix) - 1
    body = "".join(str(secrets.randbelow(10)) for _ in range(body_len))
    partial = bin_prefix + body
    return partial + str(luhn_checksum_of_partial(partial))


def bin_of(pan: str) -> str:
    """Devuelve los primeros 6 digitos (BIN/IIN)."""
    return pan[:6]
