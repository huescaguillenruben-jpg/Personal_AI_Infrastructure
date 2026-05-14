"""HSM simulado y operaciones criptograficas estilo EMV.

DECISION EDUCATIVA: el EMV real usa 3DES con jerarquia de llaves:
    IMK_AC  (Issuer Master Key)
        -> MK_AC_card  = 3DES-derive(IMK_AC, PAN || PSN)
            -> SK_AC   = 3DES-derive(MK_AC_card, ATC || UN)
                -> ARQC = 3DES-MAC(SK_AC, transaction data)

Aqui replicamos esa jerarquia con HMAC-SHA256 truncado, que es mas
sencillo de leer en Python y conceptualmente equivalente. La estructura
de derivacion (IMK -> MK_card -> SK) es real; el primitivo cambia.

En un banco de verdad, IMK_AC vive dentro de un HSM certificado (FIPS
140-2 nivel 3+) y NUNCA sale en claro. Aqui lo guardamos en memoria.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets


# ---------------------------------------------------------------------------
# Primitivos
# ---------------------------------------------------------------------------

def _mac(key: bytes, data: bytes, n_bytes: int = 16) -> bytes:
    """HMAC-SHA256 truncado. En EMV real esto seria 3DES-MAC."""
    return hmac.new(key, data, hashlib.sha256).digest()[:n_bytes]


def random_key(n_bytes: int = 32) -> bytes:
    return secrets.token_bytes(n_bytes)


def const_time_eq(a: bytes | str, b: bytes | str) -> bool:
    if isinstance(a, str): a = a.encode()
    if isinstance(b, str): b = b.encode()
    return hmac.compare_digest(a, b)


# ---------------------------------------------------------------------------
# HSM: las llaves no salen, solo se invocan operaciones
# ---------------------------------------------------------------------------

class HSM:
    """Modulo de Seguridad de Hardware simulado.

    Reglas:
      * Las llaves maestras se generan adentro y NUNCA se exponen.
      * El servidor del emisor solo puede pedir operaciones (derivar,
        firmar, verificar). Eso replica como funciona un HSM real.
    """

    def __init__(self):
        # Llaves maestras del emisor
        self._imk_ac: bytes = random_key()      # para ARQC (Application Cryptogram)
        self._imk_smc: bytes = random_key()     # para Secure Messaging Confidentiality
        self._imk_smi: bytes = random_key()     # para Secure Messaging Integrity
        self._cvv_key: bytes = random_key()     # llave para generar/verificar CVV
        self._pin_key: bytes = random_key()
        # Llaves de token: una por TSP
        self._token_keys: dict[str, bytes] = {}

    # --- CVV ---------------------------------------------------------------
    def gen_cvv(self, pan: str, expiry_mmYY: str, service_code: str = "201") -> str:
        """CVV2 (3 digitos). El algoritmo real es CVV/CVK definido por Visa."""
        mac = _mac(self._cvv_key, f"{pan}|{expiry_mmYY}|{service_code}".encode(), 4)
        n = int.from_bytes(mac, "big") % 1000
        return f"{n:03d}"

    def verify_cvv(self, pan: str, expiry_mmYY: str, cvv: str,
                   service_code: str = "201") -> bool:
        return const_time_eq(self.gen_cvv(pan, expiry_mmYY, service_code), cvv)

    # --- EMV ---------------------------------------------------------------
    def derive_icc_mk_ac(self, pan: str, psn: int) -> bytes:
        """MK_AC de la tarjeta. Cada tarjeta tiene la suya."""
        return _mac(self._imk_ac, f"MK_AC|{pan}|{psn:02d}".encode(), 16)

    def derive_session_key(self, icc_mk: bytes, atc: int, un: bytes) -> bytes:
        """SK_AC para esta transaccion. ATC + UN garantizan unicidad."""
        return _mac(icc_mk, f"SK|{atc:04d}|".encode() + un, 16)

    def compute_arqc(self, pan: str, psn: int, atc: int, un: bytes,
                     amount_minor: int, currency: str, country: str,
                     mcc: str, nonce: bytes = b"") -> str:
        """ARQC = MAC sobre datos de la transaccion.

        El chip de una tarjeta real ejecuta esto adentro y devuelve el
        ARQC al terminal, que lo manda en DE 55 hasta el emisor.
        """
        mk = self.derive_icc_mk_ac(pan, psn)
        sk = self.derive_session_key(mk, atc, un)
        data = (
            f"AMT={amount_minor}|CUR={currency}|CTY={country}|"
            f"MCC={mcc}|ATC={atc:04d}|".encode() + un + nonce
        )
        return _mac(sk, data, 8).hex().upper()   # 16 hex chars = 8 bytes

    def verify_arqc(self, arqc_hex: str, pan: str, psn: int, atc: int,
                    un: bytes, amount_minor: int, currency: str,
                    country: str, mcc: str, nonce: bytes = b"") -> bool:
        expected = self.compute_arqc(pan, psn, atc, un, amount_minor,
                                     currency, country, mcc, nonce)
        return const_time_eq(expected, arqc_hex)

    # --- Tokenizacion (TSP) -----------------------------------------------
    def provision_token_key(self, tsp_id: str) -> bytes:
        """Cada TSP (Visa VTS, Mastercard MDES) tiene su llave."""
        k = self._token_keys.get(tsp_id)
        if k is None:
            k = random_key()
            self._token_keys[tsp_id] = k
        return k

    def compute_token_cryptogram(self, device_key: bytes, dpan: str,
                                 amount_minor: int, nonce: str) -> str:
        return _mac(device_key,
                    f"{dpan}|{amount_minor}|{nonce}".encode(), 16).hex()

    def verify_token_cryptogram(self, cryptogram: str, device_key: bytes,
                                dpan: str, amount_minor: int,
                                nonce: str) -> bool:
        expected = self.compute_token_cryptogram(device_key, dpan,
                                                 amount_minor, nonce)
        return const_time_eq(expected, cryptogram)
