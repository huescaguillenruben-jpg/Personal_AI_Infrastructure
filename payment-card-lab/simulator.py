"""
Laboratorio educativo de tarjetas de pago.

NO se conecta a ninguna red real (Visa, Mastercard, bancos, Apple Pay, Google Pay).
Todo ocurre en memoria, en este proceso. Sirve para entender el flujo:

    Cliente -> Tarjeta -> Comercio -> Adquirente -> Red -> Emisor -> respuesta

Y además cómo un wallet del celular reemplaza el PAN por un DPAN (token)
con un criptograma de un solo uso.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 1. Algoritmo de Luhn
# ---------------------------------------------------------------------------
# Es público (ISO/IEC 7812). Lo usan todas las marcas (Visa, Mastercard, Amex)
# como simple checksum para detectar errores de tipeo. NO valida fondos ni
# autenticidad: un PAN puede pasar Luhn y aun así no existir en ningún banco.

def luhn_checksum(number_without_check: str) -> int:
    total = 0
    # Recorremos de derecha a izquierda, duplicando uno sí y uno no.
    for i, ch in enumerate(reversed(number_without_check)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def luhn_valid(pan: str) -> bool:
    if not pan.isdigit() or len(pan) < 12:
        return False
    return luhn_checksum(pan[:-1]) == int(pan[-1])


def generate_pan(bin_prefix: str, length: int = 16) -> str:
    """Genera un PAN sintético con un BIN dado. Solo para esta simulación."""
    body_len = length - len(bin_prefix) - 1
    body = "".join(str(secrets.randbelow(10)) for _ in range(body_len))
    partial = bin_prefix + body
    return partial + str(luhn_checksum(partial))


# ---------------------------------------------------------------------------
# 2. Cuenta y tarjeta (lado del emisor)
# ---------------------------------------------------------------------------

@dataclass
class Account:
    account_id: str
    balance_cents: int
    currency: str = "MXN"


@dataclass
class Card:
    pan: str          # Primary Account Number (16 dígitos)
    expiry: str       # MM/YY
    cvv: str          # 3 dígitos, NO se guarda hasheado en el emisor real,
                      # se valida contra HSM. Aquí lo simplificamos.
    holder: str
    account_id: str
    active: bool = True


# ---------------------------------------------------------------------------
# 3. Emisor (el banco que da la tarjeta)
# ---------------------------------------------------------------------------
# El emisor es la única autoridad que sabe el saldo. Una tarjeta por sí sola
# no "tiene fondos": los fondos viven en la cuenta a la que la tarjeta apunta.

@dataclass
class AuthResult:
    approved: bool
    code: str          # 00 = aprobada, 05 = rechazo genérico, 51 = fondos insuficientes, etc.
    message: str
    auth_id: str | None = None


class Issuer:
    BIN = "453219"  # BIN sintético para este lab (en la realidad lo asigna la marca)

    def __init__(self, name: str, hsm_secret: bytes | None = None):
        self.name = name
        self.accounts: dict[str, Account] = {}
        self.cards: dict[str, Card] = {}            # PAN -> Card
        self.tokens: dict[str, dict] = {}           # DPAN -> {pan, device_id, key}
        # En un banco real esta llave vive en un HSM físico certificado.
        self.hsm_secret = hsm_secret or secrets.token_bytes(32)

    # ---- alta de cuenta y emisión de tarjeta ----
    def open_account(self, initial_deposit_cents: int) -> Account:
        acc = Account(account_id=secrets.token_hex(4), balance_cents=initial_deposit_cents)
        self.accounts[acc.account_id] = acc
        return acc

    def issue_card(self, account_id: str, holder: str) -> Card:
        if account_id not in self.accounts:
            raise ValueError("La cuenta no existe en este emisor")
        card = Card(
            pan=generate_pan(self.BIN),
            expiry="12/29",
            cvv=f"{secrets.randbelow(1000):03d}",
            holder=holder,
            account_id=account_id,
        )
        self.cards[card.pan] = card
        return card

    # ---- autorización con tarjeta física (PAN + CVV) ----
    def authorize(self, pan: str, expiry: str, cvv: str, amount_cents: int) -> AuthResult:
        if not luhn_valid(pan):
            return AuthResult(False, "14", "PAN invalido (Luhn)")
        card = self.cards.get(pan)
        if card is None:
            return AuthResult(False, "14", "Tarjeta no emitida por este banco")
        if not card.active:
            return AuthResult(False, "05", "Tarjeta inactiva")
        if card.expiry != expiry:
            return AuthResult(False, "54", "Vencimiento incorrecto")
        if card.cvv != cvv:
            return AuthResult(False, "82", "CVV incorrecto")
        acc = self.accounts[card.account_id]
        if acc.balance_cents < amount_cents:
            return AuthResult(False, "51", "Fondos insuficientes")
        # Aprobamos: bloqueamos el monto del saldo disponible.
        acc.balance_cents -= amount_cents
        return AuthResult(True, "00", "Aprobada", auth_id=secrets.token_hex(6))

    # ---- aprovisionamiento en wallet (tokenización) ----
    # Cuando agregas una tarjeta a Apple Pay / Google Pay, el banco emisor
    # te entrega un DPAN (Device PAN): un numero distinto al PAN real,
    # ligado a UN dispositivo, mas una llave criptografica que vive en el
    # Secure Element del telefono.
    def provision_token(self, pan: str, expiry: str, cvv: str, device_id: str) -> tuple[str, bytes]:
        auth = self.authorize(pan, expiry, cvv, amount_cents=0)
        if not auth.approved:
            raise PermissionError(f"No se puede tokenizar: {auth.message}")
        # Reembolsamos el 0 que cobramos (no afecta) y emitimos token.
        dpan = generate_pan(self.BIN)
        device_key = secrets.token_bytes(32)
        self.tokens[dpan] = {"pan": pan, "device_id": device_id, "key": device_key}
        return dpan, device_key

    # ---- autorización con tap (DPAN + criptograma) ----
    def authorize_token(self, dpan: str, cryptogram: str, nonce: str,
                        amount_cents: int) -> AuthResult:
        tok = self.tokens.get(dpan)
        if tok is None:
            return AuthResult(False, "14", "DPAN desconocido")
        # Reconstruimos el criptograma esperado con la llave del dispositivo.
        expected = hmac.new(
            tok["key"],
            f"{dpan}|{amount_cents}|{nonce}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, cryptogram):
            return AuthResult(False, "05", "Criptograma invalido (replay o tampering)")
        # Va contra la cuenta del PAN real, no del DPAN.
        card = self.cards[tok["pan"]]
        acc = self.accounts[card.account_id]
        if acc.balance_cents < amount_cents:
            return AuthResult(False, "51", "Fondos insuficientes")
        acc.balance_cents -= amount_cents
        return AuthResult(True, "00", "Aprobada (NFC)", auth_id=secrets.token_hex(6))


# ---------------------------------------------------------------------------
# 4. Wallet del celular
# ---------------------------------------------------------------------------
# En un telefono real, la llave nunca sale del Secure Element / TEE.
# Aqui la guardamos en memoria solo para que veas como se usa.

class MobileWallet:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self._tokens: dict[str, dict] = {}   # DPAN -> {expiry, key, issuer}

    def add_card(self, issuer: Issuer, pan: str, expiry: str, cvv: str) -> str:
        dpan, key = issuer.provision_token(pan, expiry, cvv, self.device_id)
        self._tokens[dpan] = {"expiry": expiry, "key": key, "issuer": issuer}
        return dpan

    def tap_to_pay(self, dpan: str, amount_cents: int) -> AuthResult:
        t = self._tokens[dpan]
        nonce = secrets.token_hex(8)
        cryptogram = hmac.new(
            t["key"],
            f"{dpan}|{amount_cents}|{nonce}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return t["issuer"].authorize_token(dpan, cryptogram, nonce, amount_cents)


# ---------------------------------------------------------------------------
# 5. Comercio (lo que ve la terminal en la tienda)
# ---------------------------------------------------------------------------

@dataclass
class Merchant:
    name: str
    acquirer_issuer: Issuer   # En la vida real serian entidades distintas.

    def charge_card(self, pan, expiry, cvv, amount_cents) -> AuthResult:
        # La terminal manda los datos al adquirente, que los rutea al emisor.
        return self.acquirer_issuer.authorize(pan, expiry, cvv, amount_cents)


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------

def demo():
    print("=" * 60)
    print(" LABORATORIO DE TARJETAS DE PAGO  (todo es simulado)")
    print("=" * 60)

    bank = Issuer("BancoLab")
    store = Merchant("CafeDemo", acquirer_issuer=bank)

    # 1) Abrimos cuenta con $500.00 MXN
    acc = bank.open_account(initial_deposit_cents=50_000)
    print(f"\n[1] Cuenta abierta {acc.account_id} con saldo ${acc.balance_cents/100:.2f}")

    # 2) Emitimos una tarjeta para esa cuenta
    card = bank.issue_card(acc.account_id, holder="Ruben Huesca")
    print(f"[2] Tarjeta emitida:")
    print(f"     PAN     : {card.pan}   (Luhn valido: {luhn_valid(card.pan)})")
    print(f"     Expiry  : {card.expiry}")
    print(f"     CVV     : {card.cvv}")
    print(f"     Titular : {card.holder}")

    # 3) Compra fisica de $120.00 -> aprobada
    r = store.charge_card(card.pan, card.expiry, card.cvv, 12_000)
    print(f"\n[3] Compra $120.00 -> {r.code} {r.message}  saldo=${acc.balance_cents/100:.2f}")

    # 4) Mismo intento con CVV incorrecto -> rechazada
    r = store.charge_card(card.pan, card.expiry, "000", 5_000)
    print(f"[4] CVV mal      -> {r.code} {r.message}")

    # 5) Intento por arriba del saldo -> 51
    r = store.charge_card(card.pan, card.expiry, card.cvv, 999_999)
    print(f"[5] Sin fondos   -> {r.code} {r.message}")

    # 6) Agregar la tarjeta al wallet del celular -> obtenemos un DPAN
    phone = MobileWallet(device_id="iPhone-de-Ruben")
    dpan = phone.add_card(bank, card.pan, card.expiry, card.cvv)
    print(f"\n[6] Tarjeta agregada al wallet")
    print(f"     PAN real (no sale del banco)    : {card.pan}")
    print(f"     DPAN en el telefono             : {dpan}")
    print(f"     -> si te roban el celular y clonan el DPAN, el banco lo apaga")
    print(f"        sin tener que reemplazar la tarjeta fisica.")

    # 7) Tap to pay con NFC: el telefono firma un criptograma de un solo uso
    r = phone.tap_to_pay(dpan, 7_500)
    print(f"\n[7] Tap NFC $75.00 -> {r.code} {r.message}  saldo=${acc.balance_cents/100:.2f}")

    # 8) Intento de replay: reusar el mismo criptograma -> el nonce cambia
    #    asi que reconstruir el ataque requiere la llave del Secure Element,
    #    que no salio del dispositivo. Esto es lo que hace seguro a Apple/Google Pay.
    fake_crypto = "deadbeef" * 8
    r = bank.authorize_token(dpan, fake_crypto, nonce="x", amount_cents=10_000)
    print(f"[8] Intento de pago con criptograma falso -> {r.code} {r.message}")

    print("\n" + "=" * 60)
    print(" Saldo final de la cuenta: ${:.2f}".format(acc.balance_cents/100))
    print("=" * 60)


if __name__ == "__main__":
    demo()
