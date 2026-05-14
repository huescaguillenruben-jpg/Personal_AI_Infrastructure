"""Dataclasses del dominio.

Decision de diseno: los modelos son "anemios" (solo datos). La logica
vive en los servicios (Issuer, Acquirer, Network, etc.) porque queremos
que sea claro donde ocurre cada decision.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .lifecycle import CardStatus


# ---------------------------------------------------------------------------
# Identidad
# ---------------------------------------------------------------------------

@dataclass
class Holder:
    """Persona/empresa duena de una cuenta."""
    holder_id: str
    full_name: str
    country_iso2: str = "MX"   # ISO 3166-1 alpha-2
    kyc_verified: bool = True  # en la vida real esto cuelga de KYC/AML


# ---------------------------------------------------------------------------
# Dinero
# ---------------------------------------------------------------------------

@dataclass
class Money:
    """Cantidad de dinero en la unidad menor (centavos)."""
    amount_minor: int
    currency: str = "MXN"

    def __str__(self) -> str:
        return f"{self.amount_minor / 100:.2f} {self.currency}"

    def __add__(self, other: "Money") -> "Money":
        assert self.currency == other.currency
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        assert self.currency == other.currency
        return Money(self.amount_minor - other.amount_minor, self.currency)


# ---------------------------------------------------------------------------
# Cuenta y tarjeta
# ---------------------------------------------------------------------------

class AccountType(str, Enum):
    CHECKING = "checking"   # debito
    CREDIT = "credit"       # credito (limite, no saldo)


@dataclass
class Account:
    account_id: str
    holder_id: str
    account_type: AccountType
    currency: str = "MXN"
    # Para CHECKING: saldo real. Para CREDIT: monto ya gastado (positivo = deuda).
    posted_minor: int = 0
    # Holds (autorizaciones aun no liquidadas).
    held_minor: int = 0
    # Solo CREDIT: limite total.
    credit_limit_minor: int = 0
    closed: bool = False

    def available_minor(self) -> int:
        if self.account_type == AccountType.CHECKING:
            return self.posted_minor - self.held_minor
        # credito: limite - (gastado + held)
        return self.credit_limit_minor - self.posted_minor - self.held_minor


class POSEntryMode(str, Enum):
    """ISO 8583 DE 22 simplificado."""
    MANUAL = "manual"          # tarjeta no presente, datos tipeados
    SWIPE = "swipe"            # banda magnetica
    CHIP = "chip"              # EMV insertado
    CONTACTLESS = "contactless"   # NFC plastico
    NFC_WALLET = "nfc_wallet"  # NFC desde wallet movil (tokenizado)
    ECOMMERCE = "ecommerce"    # CNP (card not present)
    RECURRING = "recurring"


@dataclass
class Card:
    """Tarjeta fisica/virtual emitida."""
    pan: str
    expiry_mmYY: str          # MM/YY
    cvv: str                  # nunca exponer
    card_seq_num: int         # PSN (PAN Sequence Number) para EMV
    holder_id: str
    account_id: str
    status: CardStatus = CardStatus.ISSUED
    issued_at_ts: float = field(default_factory=time.time)
    # ATC (Application Transaction Counter) del chip, incrementa por compra EMV.
    atc: int = 0


@dataclass
class Token:
    """DPAN (Device PAN) emitido por el TSP, ligado a un dispositivo."""
    dpan: str
    real_pan: str
    device_id: str
    wallet_provider: str        # apple_pay, google_pay, samsung_pay, etc.
    token_key: bytes            # llave HMAC del Secure Element
    status: CardStatus = CardStatus.ACTIVE
    created_ts: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Transacciones
# ---------------------------------------------------------------------------

class TxnState(str, Enum):
    AUTHORIZED = "authorized"     # hold puesto
    CAPTURED = "captured"         # capturada/posted, lista para liquidar
    SETTLED = "settled"           # liquidada (fondos en cuenta del comercio)
    REVERSED = "reversed"         # auth reversada antes de capture
    REFUNDED = "refunded"
    DECLINED = "declined"


@dataclass
class Transaction:
    txn_id: str
    stan: int                      # System Trace Audit Number (DE 11)
    rrn: str                       # Retrieval Reference Number (DE 37)
    pan_masked: str
    amount: Money
    mcc: str                       # Merchant Category Code (DE 18)
    merchant_id: str
    terminal_id: str
    pos_entry: POSEntryMode
    country_iso2: str              # pais del comercio
    state: TxnState
    response_code: str             # ISO 8583 DE 39
    auth_code: Optional[str] = None  # DE 38 (6 chars cuando aprobada)
    captured_amount: Optional[Money] = None
    timestamp: float = field(default_factory=time.time)
    # Datos opcionales segun canal:
    emv_data: Optional[dict] = None   # ARQC, ATC, etc.
    threeds_cavv: Optional[str] = None
    dpan_used: Optional[str] = None
    fraud_score: int = 0


# ---------------------------------------------------------------------------
# Solicitudes
# ---------------------------------------------------------------------------

@dataclass
class AuthRequest:
    """Lo que el comercio/terminal manda al adquirente."""
    pan: str
    expiry_mmYY: str
    cvv: Optional[str]
    amount: Money
    mcc: str
    merchant_id: str
    terminal_id: str
    pos_entry: POSEntryMode
    country_iso2: str
    # opcionales por canal
    emv: Optional[dict] = None
    cavv: Optional[str] = None       # 3DS
    cryptogram: Optional[str] = None   # NFC wallet
    nonce: Optional[str] = None        # NFC wallet
    dpan: Optional[str] = None         # NFC wallet
    stan: int = 0
    rrn: str = ""


def new_stan() -> int:
    return secrets.randbelow(1_000_000)


def new_rrn() -> str:
    return f"{secrets.randbelow(10**12):012d}"


def new_auth_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"
