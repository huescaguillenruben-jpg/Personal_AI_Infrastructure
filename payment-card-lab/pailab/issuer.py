"""Issuer (banco emisor).

Encapsula:
  * HSM (llaves), Ledger (cuentas), FraudEngine (reglas), ACS (3DS), TSP (tokens).
  * Emision de cuentas y tarjetas.
  * Autorizacion / captura / reverso / refund por canal (MAG, EMV, CNP, NFC tokenizado).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from .crypto import HSM, const_time_eq
from .errors import RC, message
from .fraud import FraudDecision, FraudEngine
from .iso8583 import DE, MTI, Iso8583Message
from .ledger import InsufficientFundsError, Ledger
from .lifecycle import CardStatus, can_transition, is_usable
from .logging_utils import get_logger, mask_pan
from .luhn import bin_of, generate_pan, luhn_valid
from .models import (
    Account, AccountType, AuthRequest, Card, Holder, Money,
    POSEntryMode, Transaction, TxnState,
    new_auth_code, new_id, new_rrn, new_stan,
)
from .tds import ACS, ThreeDSResult
from .tsp import TSP


log = get_logger("issuer")


def _rc_for_fraud(reasons: list[str]) -> RC:
    """Mapea la razon primaria del motor antifraude a un RC ISO 8583."""
    txt = " ".join(reasons).lower()
    if "limite diario" in txt or "excede limite" in txt:
        return RC.EXCEEDS_WITHDRAWAL_LIMIT
    if "velocidad" in txt:
        return RC.EXCEEDS_FREQ_LIMIT
    if "bloqueado" in txt:
        return RC.RESTRICTED_CARD
    return RC.DO_NOT_HONOR


@dataclass
class IssuerConfig:
    name: str
    bin: str = "453219"
    country_iso2: str = "MX"
    currency: str = "MXN"


@dataclass
class AuthOutcome:
    approved: bool
    rc: RC
    message: str
    txn: Transaction | None = None
    threeds_challenge: tuple[str, str] | None = None   # (challenge_id, otp)


class Issuer:
    def __init__(self, config: IssuerConfig, tsp: TSP | None = None):
        self.config = config
        self.hsm = HSM()
        self.ledger = Ledger()
        self.fraud = FraudEngine()
        self.acs = ACS()
        self.tsp = tsp or TSP(name=f"TSP-of-{config.name}", hsm=self.hsm)
        self.issuer_id = new_id("iss")
        self.holders: dict[str, Holder] = {}
        self.cards: dict[str, Card] = {}             # pan -> Card
        self.transactions: dict[str, Transaction] = {}

    # ----- alta de clientes / cuentas / tarjetas -------------------------
    def register_holder(self, full_name: str, country_iso2: str | None = None) -> Holder:
        h = Holder(holder_id=new_id("hld"), full_name=full_name,
                   country_iso2=country_iso2 or self.config.country_iso2)
        self.holders[h.holder_id] = h
        return h

    def open_account(self, holder: Holder, account_type: AccountType,
                     initial_deposit: Money | None = None,
                     credit_limit: Money | None = None) -> Account:
        acc = Account(
            account_id=new_id("acc"),
            holder_id=holder.holder_id,
            account_type=account_type,
            currency=self.config.currency,
            credit_limit_minor=credit_limit.amount_minor if credit_limit else 0,
        )
        self.ledger.open(acc)
        if initial_deposit and account_type == AccountType.CHECKING:
            self.ledger.deposit(acc.account_id, initial_deposit,
                                memo="apertura")
        return acc

    def issue_card(self, account: Account) -> Card:
        holder = self.holders[account.holder_id]
        pan = generate_pan(self.config.bin)
        # expiry a 5 anos
        exp_struct = time.gmtime(time.time() + 5 * 365 * 86400)
        expiry = time.strftime("%m/%y", exp_struct)
        cvv = self.hsm.gen_cvv(pan, expiry)
        card = Card(
            pan=pan,
            expiry_mmYY=expiry,
            cvv=cvv,
            card_seq_num=1,
            holder_id=holder.holder_id,
            account_id=account.account_id,
            status=CardStatus.ISSUED,
        )
        self.cards[pan] = card
        self.fraud.declare_home_country(pan, holder.country_iso2)
        log.info("Tarjeta emitida pan=%s exp=%s holder=%s",
                 mask_pan(pan), expiry, holder.full_name)
        return card

    def activate_card(self, pan: str) -> None:
        card = self.cards[pan]
        if not can_transition(card.status, CardStatus.ACTIVE):
            raise ValueError(f"no se puede activar desde {card.status}")
        card.status = CardStatus.ACTIVE
        log.info("Tarjeta activada pan=%s", mask_pan(pan))

    def set_card_status(self, pan: str, new_status: CardStatus) -> None:
        card = self.cards[pan]
        if not can_transition(card.status, new_status):
            raise ValueError(f"transicion invalida {card.status}->{new_status}")
        card.status = new_status
        if new_status in (CardStatus.LOST, CardStatus.STOLEN, CardStatus.BLOCKED):
            self.fraud.block_pan(pan)
            # Suspende DPANs ligados
            for tok in self.tsp.tokens_of(pan):
                self.tsp.suspend(tok.dpan)
        log.info("Tarjeta pan=%s -> %s", mask_pan(pan), new_status)

    # ----- proxy tokenizacion (el TSP es el que emite) -------------------
    def provision_token(self, pan: str, expiry_mmYY: str, cvv: str,
                        device_id: str, wallet_provider: str):
        card = self.cards.get(pan)
        if not card or not is_usable(card.status):
            raise PermissionError("Tarjeta no usable")
        if card.expiry_mmYY != expiry_mmYY:
            raise PermissionError("Vencimiento incorrecto")
        if not self.hsm.verify_cvv(pan, expiry_mmYY, cvv):
            raise PermissionError("CVV incorrecto")
        return self.tsp.provision(
            issuer_id=self.issuer_id, pan_real=pan,
            device_id=device_id, wallet_provider=wallet_provider,
        )

    # ----- autorizacion ---------------------------------------------------
    def authorize(self, req: AuthRequest) -> AuthOutcome:
        """Punto de entrada principal. Aplica todas las reglas."""
        if not req.stan:
            req.stan = new_stan()
        if not req.rrn:
            req.rrn = new_rrn()

        # 0) Si viene por DPAN, detokenizar primero.
        if req.pos_entry == POSEntryMode.NFC_WALLET:
            return self._authorize_tokenized(req)

        # 1) Validar Luhn (DE 39 = 14)
        if not luhn_valid(req.pan):
            return self._decline(req, RC.INVALID_CARD, "PAN invalido (Luhn)")

        card = self.cards.get(req.pan)
        if not card:
            return self._decline(req, RC.NO_ISSUER, "Tarjeta no del emisor")
        if not is_usable(card.status):
            rc = RC.LOST_CARD if card.status == CardStatus.LOST else \
                 RC.STOLEN_CARD if card.status == CardStatus.STOLEN else \
                 RC.DO_NOT_HONOR
            return self._decline(req, rc, f"estado tarjeta={card.status}")

        # 2) Vencimiento
        if card.expiry_mmYY != req.expiry_mmYY:
            return self._decline(req, RC.EXPIRED_CARD, "Vencimiento incorrecto")

        # 3) CVV (solo si lo mandaron — los EMV/NFC suelen no incluirlo)
        if req.cvv is not None and not self.hsm.verify_cvv(
                req.pan, req.expiry_mmYY, req.cvv):
            return self._decline(req, RC.INVALID_CVV, "CVV incorrecto")

        # 4) Reglas antifraude
        decision = self.fraud.evaluate(req)
        if decision.decline:
            return self._decline(req, _rc_for_fraud(decision.reasons),
                                 f"antifraude: {'; '.join(decision.reasons)}")
        if decision.require_3ds and not req.cavv:
            cid, otp = self.acs.initiate(req.pan, req.amount.amount_minor)
            log.info("3DS challenge requerido pan=%s cid=%s",
                     mask_pan(req.pan), cid)
            out = AuthOutcome(approved=False, rc=RC.SOFT_DECLINE_SCA_REQUIRED,
                              message=message(RC.SOFT_DECLINE_SCA_REQUIRED),
                              threeds_challenge=(cid, otp))
            return out

        # 5) Si trae CAVV, verificarlo
        if req.cavv:
            # En la realidad el CAVV viaja en DE 112 y el ACS lo valida sin
            # necesidad de un challenge_id explicito: aqui pedimos que el
            # caller lo guarde como `req.emv['cavv_cid']` si quiere validar.
            cid = (req.emv or {}).get("cavv_cid", "")
            if not self.acs.verify_cavv(req.cavv, req.pan,
                                        req.amount.amount_minor, cid):
                return self._decline(req, RC.CARDHOLDER_AUTH_FAILED, "CAVV invalido")

        # 6) EMV ARQC (canal chip o contactless plastico)
        if req.pos_entry in (POSEntryMode.CHIP, POSEntryMode.CONTACTLESS):
            if not req.emv:
                return self._decline(req, RC.CRYPTO_FAILURE, "EMV sin datos")
            arqc = req.emv.get("arqc", "")
            atc = int(req.emv.get("atc", 0))
            un = bytes.fromhex(req.emv.get("un", "00000000"))
            ok = self.hsm.verify_arqc(
                arqc, req.pan, card.card_seq_num, atc, un,
                req.amount.amount_minor, req.amount.currency,
                req.country_iso2, req.mcc,
            )
            if not ok:
                return self._decline(req, RC.CRYPTO_FAILURE, "ARQC invalido")
            # Anti-replay: ATC siempre crece.
            if atc <= card.atc:
                return self._decline(req, RC.CRYPTO_FAILURE,
                                     f"ATC replay (atc={atc}, last={card.atc})")
            card.atc = atc

        # 7) Hold en ledger
        try:
            self.ledger.hold(card.account_id, req.amount, txn_id=req.rrn,
                             memo=f"auth {req.merchant_id}")
        except InsufficientFundsError as e:
            return self._decline(req, RC.INSUFFICIENT_FUNDS, str(e))

        # 8) Aprobada
        self.fraud.record_approved(req)
        self.fraud.reset_declines(req.pan)
        return self._approve(req, decision)

    def _authorize_tokenized(self, req: AuthRequest) -> AuthOutcome:
        if not req.dpan or not req.cryptogram or not req.nonce:
            return self._decline(req, RC.CRYPTO_FAILURE, "Datos NFC incompletos")
        rec = self.tsp.get_record(req.dpan)
        if not rec or rec.issuer_id != self.issuer_id:
            return self._decline(req, RC.NO_ISSUER, "DPAN desconocido")
        if rec.token.status != CardStatus.ACTIVE:
            return self._decline(req, RC.RESTRICTED_CARD, "DPAN no activo")
        if not self.hsm.verify_token_cryptogram(
                req.cryptogram, rec.token.token_key, req.dpan,
                req.amount.amount_minor, req.nonce):
            return self._decline(req, RC.CRYPTO_FAILURE,
                                 "Criptograma de token invalido")
        # Detokenizar para hacer el resto del flujo con el PAN real.
        real_pan = rec.pan_real
        new_req = AuthRequest(
            pan=real_pan,
            expiry_mmYY=self.cards[real_pan].expiry_mmYY,
            cvv=None,                        # NFC no manda CVV
            amount=req.amount,
            mcc=req.mcc,
            merchant_id=req.merchant_id,
            terminal_id=req.terminal_id,
            pos_entry=POSEntryMode.CONTACTLESS,    # se procesa como contactless plastico
            country_iso2=req.country_iso2,
            emv=None,                        # ya verificamos por token cryptogram
            stan=req.stan, rrn=req.rrn,
        )
        # No re-verificamos ARQC porque el token cryptogram cumple el rol.
        card = self.cards[real_pan]
        decision = self.fraud.evaluate(new_req)
        if decision.decline:
            return self._decline(new_req, _rc_for_fraud(decision.reasons),
                                 f"antifraude (tokenizado): {'; '.join(decision.reasons)}")
        try:
            self.ledger.hold(card.account_id, new_req.amount, txn_id=new_req.rrn,
                             memo=f"auth NFC {new_req.merchant_id}")
        except InsufficientFundsError as e:
            return self._decline(new_req, RC.INSUFFICIENT_FUNDS, str(e))
        self.fraud.record_approved(new_req)
        outcome = self._approve(new_req, decision)
        if outcome.txn:
            outcome.txn.dpan_used = req.dpan
            outcome.txn.pos_entry = POSEntryMode.NFC_WALLET
        return outcome

    # ----- decisiones / contabilidad ------------------------------------
    def _decline(self, req: AuthRequest, rc: RC, why: str) -> AuthOutcome:
        log.warning("Declinada pan=%s monto=%s rc=%s why=%s",
                    mask_pan(req.pan), req.amount, rc.value, why)
        self.fraud.record_decline(req.pan)
        txn = self._make_txn(req, state=TxnState.DECLINED, rc=rc)
        return AuthOutcome(approved=False, rc=rc, message=why, txn=txn)

    def _approve(self, req: AuthRequest, decision: FraudDecision) -> AuthOutcome:
        auth_code = new_auth_code()
        txn = self._make_txn(req, state=TxnState.AUTHORIZED, rc=RC.APPROVED,
                             auth_code=auth_code, fraud_score=decision.score)
        log.info("Aprobada pan=%s monto=%s auth=%s",
                 mask_pan(req.pan), req.amount, auth_code)
        return AuthOutcome(approved=True, rc=RC.APPROVED,
                           message=message(RC.APPROVED), txn=txn)

    def _make_txn(self, req: AuthRequest, *, state: TxnState, rc: RC,
                  auth_code: str | None = None, fraud_score: int = 0) -> Transaction:
        txn = Transaction(
            txn_id=new_id("txn"),
            stan=req.stan,
            rrn=req.rrn,
            pan_masked=mask_pan(req.pan),
            amount=req.amount,
            mcc=req.mcc,
            merchant_id=req.merchant_id,
            terminal_id=req.terminal_id,
            pos_entry=req.pos_entry,
            country_iso2=req.country_iso2,
            state=state,
            response_code=rc.value,
            auth_code=auth_code,
            emv_data=req.emv,
            threeds_cavv=req.cavv,
            fraud_score=fraud_score,
        )
        self.transactions[txn.txn_id] = txn
        return txn

    # ----- captura / reverso / refund ----------------------------------
    def capture(self, txn_id: str, amount: Money | None = None) -> bool:
        """Captura una autorizacion (clearing batch o capture en linea)."""
        txn = self.transactions[txn_id]
        if txn.state != TxnState.AUTHORIZED:
            raise ValueError(f"txn no autorizada (state={txn.state})")
        capture_amt = amount or txn.amount
        # Buscar account
        pan = self._pan_of_txn(txn)
        card = self.cards[pan]
        self.ledger.post(card.account_id, txn.amount, capture_amt,
                         txn_id=txn.rrn, memo=f"capture {txn.merchant_id}")
        txn.state = TxnState.CAPTURED
        txn.captured_amount = capture_amt
        log.info("Capturada txn=%s monto=%s", txn.txn_id, capture_amt)
        return True

    def reverse(self, txn_id: str) -> bool:
        txn = self.transactions[txn_id]
        if txn.state not in (TxnState.AUTHORIZED, TxnState.CAPTURED):
            raise ValueError(f"no se puede reversar en state={txn.state}")
        pan = self._pan_of_txn(txn)
        card = self.cards[pan]
        if txn.state == TxnState.AUTHORIZED:
            self.ledger.release(card.account_id, txn.amount, txn_id=txn.rrn,
                                memo=f"reverse auth {txn.merchant_id}")
        else:
            # Ya capturada: reembolsar
            self.ledger.refund(card.account_id,
                               txn.captured_amount or txn.amount,
                               txn_id=txn.rrn,
                               memo=f"reverse capture {txn.merchant_id}")
        txn.state = TxnState.REVERSED
        log.info("Reversada txn=%s", txn.txn_id)
        return True

    def refund(self, txn_id: str, amount: Money | None = None) -> bool:
        txn = self.transactions[txn_id]
        if txn.state not in (TxnState.CAPTURED, TxnState.SETTLED):
            raise ValueError(f"no se puede refund en state={txn.state}")
        pan = self._pan_of_txn(txn)
        card = self.cards[pan]
        amt = amount or txn.captured_amount or txn.amount
        self.ledger.refund(card.account_id, amt, txn_id=txn.rrn,
                           memo=f"refund {txn.merchant_id}")
        if (txn.captured_amount and amt.amount_minor >= txn.captured_amount.amount_minor):
            txn.state = TxnState.REFUNDED
        log.info("Refund txn=%s monto=%s", txn.txn_id, amt)
        return True

    def _pan_of_txn(self, txn: Transaction) -> str:
        # Cuando tokenizada, mapeamos por DPAN
        if txn.dpan_used:
            return self.tsp.get_record(txn.dpan_used).pan_real
        # Si no, buscamos por mask + ultimos 4
        last4 = txn.pan_masked[-4:]
        first6 = txn.pan_masked[:6]
        for pan in self.cards:
            if pan.startswith(first6) and pan.endswith(last4):
                return pan
        raise KeyError("No se encontro PAN para la transaccion")
