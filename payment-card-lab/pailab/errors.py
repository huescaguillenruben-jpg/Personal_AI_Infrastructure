"""Codigos de respuesta ISO 8583 (subset relevante).

Se usan en DE 39 de la respuesta. Lista oficial mucho mas larga; aqui
incluimos los que aparecen en el flujo del lab.
"""

from __future__ import annotations

from enum import Enum


class RC(str, Enum):
    APPROVED = "00"
    REFER_TO_ISSUER = "01"
    INVALID_MERCHANT = "03"
    PICK_UP = "04"
    DO_NOT_HONOR = "05"
    PARTIAL_APPROVAL = "10"
    INVALID_TXN = "12"
    INVALID_AMOUNT = "13"
    INVALID_CARD = "14"
    NO_ISSUER = "15"
    LOST_CARD = "41"
    STOLEN_CARD = "43"
    INSUFFICIENT_FUNDS = "51"
    NO_CHECKING_ACCT = "52"
    EXPIRED_CARD = "54"
    INCORRECT_PIN = "55"
    EXCEEDS_WITHDRAWAL_LIMIT = "61"
    RESTRICTED_CARD = "62"
    SECURITY_VIOLATION = "63"
    EXCEEDS_FREQ_LIMIT = "65"
    SOFT_DECLINE_SCA_REQUIRED = "1A"   # PSD2 / 3DS challenge requerida
    CARDHOLDER_AUTH_FAILED = "75"
    INVALID_CVV = "82"
    CRYPTO_FAILURE = "85"
    SYSTEM_MALFUNCTION = "96"


CODE_TEXT = {
    RC.APPROVED: "Aprobada",
    RC.REFER_TO_ISSUER: "Llamar al emisor",
    RC.INVALID_MERCHANT: "Comercio invalido",
    RC.PICK_UP: "Retener tarjeta",
    RC.DO_NOT_HONOR: "No honrar",
    RC.PARTIAL_APPROVAL: "Aprobacion parcial",
    RC.INVALID_TXN: "Transaccion invalida",
    RC.INVALID_AMOUNT: "Monto invalido",
    RC.INVALID_CARD: "Tarjeta invalida",
    RC.NO_ISSUER: "Emisor no encontrado",
    RC.LOST_CARD: "Tarjeta reportada como perdida",
    RC.STOLEN_CARD: "Tarjeta reportada como robada",
    RC.INSUFFICIENT_FUNDS: "Fondos insuficientes",
    RC.NO_CHECKING_ACCT: "Cuenta inexistente",
    RC.EXPIRED_CARD: "Tarjeta vencida",
    RC.INCORRECT_PIN: "PIN incorrecto",
    RC.EXCEEDS_WITHDRAWAL_LIMIT: "Excede limite",
    RC.RESTRICTED_CARD: "Tarjeta restringida",
    RC.SECURITY_VIOLATION: "Violacion de seguridad",
    RC.EXCEEDS_FREQ_LIMIT: "Excede frecuencia",
    RC.SOFT_DECLINE_SCA_REQUIRED: "Requiere autenticacion fuerte (3DS)",
    RC.CARDHOLDER_AUTH_FAILED: "Autenticacion del tarjetahabiente fallida",
    RC.INVALID_CVV: "CVV incorrecto",
    RC.CRYPTO_FAILURE: "Falla criptografica (ARQC/cryptogram)",
    RC.SYSTEM_MALFUNCTION: "Falla del sistema",
}


def message(rc: RC) -> str:
    return CODE_TEXT.get(rc, "Desconocido")
