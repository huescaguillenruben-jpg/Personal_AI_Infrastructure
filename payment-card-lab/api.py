"""HTTP API + frontend del laboratorio.

Endpoints:
    GET  /                              -> sirve web/index.html
    GET  /static/*                      -> archivos en web/
    GET  /health
    GET  /accounts/{account_id}
    GET  /transactions                  -> ultimas N txns
    POST /holders                       {full_name, country?}
    POST /accounts                      {holder_id, type, initial_deposit_minor, currency?}
    POST /cards                         {account_id}
    POST /cards/{pan}/status            {status}
    POST /authorize                     AuthRequest JSON (subset)
    POST /capture                       {txn_id}
    POST /reverse                       {txn_id}
    POST /clearing/run
    POST /wallet/provision              {pan, expiry, cvv, device_id, provider?}
    POST /wallet/tap                    {dpan, amount_minor, ...}
    POST /threeds/verify                {challenge_id, otp}

NO escuchar en red publica; uso local solamente.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from pailab.acquirer import Acquirer
from pailab.clearing import ClearingEngine
from pailab.errors import RC
from pailab.issuer import Issuer, IssuerConfig
from pailab.lifecycle import CardStatus
from pailab.logging_utils import configure_logging, mask_pan
from pailab.luhn import bin_of
from pailab.acquirer import PendingAuth
from pailab.models import AccountType, AuthRequest, Money, POSEntryMode, TxnState
from pailab.network import CardNetwork
from pailab.terminal import Terminal


# Mundo global (no se persiste, solo memoria).
configure_logging()
ISSUER = Issuer(IssuerConfig(name="ApiBank"))
ACQ = Acquirer("ApiAcq")
NET = CardNetwork("ApiNet")
NET.register_issuer(ISSUER.config.bin, ISSUER)
NET.register_tsp(ISSUER.tsp)
ACQ.network = NET
DEFAULT_MERCHANT = ACQ.onboard_merchant("Lab Storefront", mcc="5812")
DEFAULT_TERMINAL = Terminal.deploy(ACQ, DEFAULT_MERCHANT)

# Starter card: emitida al arrancar para que la UI tenga algo listo.
STARTER_HOLDER = ISSUER.register_holder("Ruben Huesca")
STARTER_ACCOUNT = ISSUER.open_account(
    STARTER_HOLDER, AccountType.CHECKING,
    initial_deposit=Money(50_000_00),     # $50,000 MXN
)
STARTER_CARD = ISSUER.issue_card(STARTER_ACCOUNT)
ISSUER.activate_card(STARTER_CARD.pan)

WEB_ROOT = os.path.join(os.path.dirname(__file__), "web")


def _txn_dict(t):
    return {
        "txn_id": t.txn_id,
        "pan_masked": t.pan_masked,
        "amount_minor": t.amount.amount_minor,
        "currency": t.amount.currency,
        "state": t.state.value,
        "response_code": t.response_code,
        "auth_code": t.auth_code,
        "pos_entry": t.pos_entry.value,
        "merchant_id": t.merchant_id,
        "timestamp": t.timestamp,
        "dpan_used": t.dpan_used,
    }


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body) -> None:
        raw = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _serve_static(self, relpath: str) -> None:
        full = os.path.normpath(os.path.join(WEB_ROOT, relpath))
        if not full.startswith(WEB_ROOT) or not os.path.isfile(full):
            return self._json(404, {"error": "not found"})
        ctype, _ = mimetypes.guess_type(full)
        ctype = ctype or "application/octet-stream"
        with open(full, "rb") as fh:
            raw = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, format, *args):
        pass

    # ----- GET ------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/" or path == "/index.html":
                return self._serve_static("index.html")
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/health":
                return self._json(200, {
                    "ok": True,
                    "issuer_bin": ISSUER.config.bin,
                    "issuer_name": ISSUER.config.name,
                    "merchant_id": DEFAULT_MERCHANT.merchant_id,
                })
            if path == "/starter":
                return self._json(200, {
                    "holder_name": STARTER_HOLDER.full_name,
                    "holder_id": STARTER_HOLDER.holder_id,
                    "account_id": STARTER_ACCOUNT.account_id,
                    "pan": STARTER_CARD.pan,
                    "expiry": STARTER_CARD.expiry_mmYY,
                    "cvv": STARTER_CARD.cvv,
                    "psn": STARTER_CARD.card_seq_num,
                    "pan_masked": mask_pan(STARTER_CARD.pan),
                })
            if path.startswith("/accounts/"):
                acc = ISSUER.ledger.get(path.split("/")[-1])
                return self._json(200, {
                    "account_id": acc.account_id,
                    "type": acc.account_type.value,
                    "currency": acc.currency,
                    "posted_minor": acc.posted_minor,
                    "held_minor": acc.held_minor,
                    "available_minor": acc.available_minor(),
                })
            if path == "/transactions":
                txns = list(ISSUER.transactions.values())[-50:]
                return self._json(200, {"transactions": [_txn_dict(t) for t in reversed(txns)]})
            self._json(404, {"error": "not found"})
        except KeyError:
            self._json(404, {"error": "resource not found"})
        except Exception as e:
            self._json(500, {"error": str(e)})

    # ----- POST -----------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read()
            if path == "/holders":
                h = ISSUER.register_holder(body["full_name"], body.get("country", "MX"))
                return self._json(200, {"holder_id": h.holder_id, "name": h.full_name})
            if path == "/accounts":
                holder = ISSUER.holders[body["holder_id"]]
                acc = ISSUER.open_account(
                    holder, AccountType(body.get("type", "checking")),
                    initial_deposit=Money(int(body.get("initial_deposit_minor", 0)),
                                          body.get("currency", "MXN")),
                )
                return self._json(200, {"account_id": acc.account_id})
            if path == "/cards":
                acc = ISSUER.ledger.get(body["account_id"])
                card = ISSUER.issue_card(acc)
                ISSUER.activate_card(card.pan)
                return self._json(200, {
                    "pan": card.pan, "expiry": card.expiry_mmYY,
                    "cvv": card.cvv, "pan_masked": mask_pan(card.pan),
                    "psn": card.card_seq_num,
                })
            if path.startswith("/cards/") and path.endswith("/status"):
                pan = path.split("/")[2]
                ISSUER.set_card_status(pan, CardStatus(body["status"]))
                return self._json(200, {"ok": True, "status": body["status"]})
            if path == "/authorize":
                pos = POSEntryMode(body.get("pos_entry", "swipe"))
                emv_data = None
                # Para canales con chip, el server simula el "chip" generando
                # el ARQC con su HSM (como pasaria en la vida real con la MK_AC
                # ya personalizada en la tarjeta).
                if pos in (POSEntryMode.CHIP, POSEntryMode.CONTACTLESS):
                    card = ISSUER.cards.get(body["pan"])
                    if card is None:
                        return self._json(400, {"error": "PAN no emitido por este banco"})
                    next_atc = card.atc + 1
                    un = secrets.token_bytes(4)
                    arqc = ISSUER.hsm.compute_arqc(
                        body["pan"], card.card_seq_num, next_atc, un,
                        int(body["amount_minor"]),
                        body.get("currency", "MXN"),
                        body.get("country", "MX"),
                        body.get("mcc", DEFAULT_MERCHANT.mcc),
                    )
                    emv_data = {"arqc": arqc, "atc": next_atc, "un": un.hex(),
                                "psn": card.card_seq_num}
                if body.get("cavv_cid"):
                    emv_data = (emv_data or {}) | {"cavv_cid": body["cavv_cid"]}
                req = AuthRequest(
                    pan=body["pan"],
                    expiry_mmYY=body["expiry"],
                    cvv=body.get("cvv"),
                    amount=Money(int(body["amount_minor"]),
                                 body.get("currency", "MXN")),
                    mcc=body.get("mcc", DEFAULT_MERCHANT.mcc),
                    merchant_id=body.get("merchant_id", DEFAULT_MERCHANT.merchant_id),
                    terminal_id=body.get("terminal_id", DEFAULT_TERMINAL.terminal_id),
                    pos_entry=pos,
                    country_iso2=body.get("country", "MX"),
                    cavv=body.get("cavv"),
                    emv=emv_data,
                )
                out = ISSUER.authorize(req)
                # Si aprueba, registrar pending en el acquirer (para clearing).
                if out.approved and out.txn:
                    ACQ.pending_auths.append(PendingAuth(
                        txn_id=out.txn.txn_id,
                        merchant_id=req.merchant_id,
                        pan_first6=body["pan"][:6],
                        amount_minor=req.amount.amount_minor,
                        currency=req.amount.currency,
                    ))
                resp = {
                    "approved": out.approved,
                    "rc": out.rc.value,
                    "message": out.message,
                    "txn_id": out.txn.txn_id if out.txn else None,
                    "auth_code": out.txn.auth_code if out.txn else None,
                }
                if out.threeds_challenge:
                    cid, otp = out.threeds_challenge
                    resp["threeds"] = {"challenge_id": cid, "otp_demo": otp}
                return self._json(200, resp)
            if path == "/capture":
                ISSUER.capture(body["txn_id"])
                # Mark on acquirer if present
                ACQ.mark_captured(body["txn_id"])
                return self._json(200, {"ok": True})
            if path == "/reverse":
                ISSUER.reverse(body["txn_id"])
                return self._json(200, {"ok": True})
            if path == "/clearing/run":
                ce = ClearingEngine(ACQ, {ISSUER.config.bin: ISSUER},
                                    tsps=[ISSUER.tsp])
                result = ce.run_batch()
                return self._json(200, result)
            if path == "/threeds/verify":
                r = ISSUER.acs.verify(body["challenge_id"], body["otp"])
                return self._json(200, {
                    "success": r.success, "cavv": r.cavv, "eci": r.eci,
                    "reason": r.reason,
                })
            if path == "/wallet/provision":
                tok = ISSUER.provision_token(
                    pan=body["pan"], expiry_mmYY=body["expiry"], cvv=body["cvv"],
                    device_id=body["device_id"],
                    wallet_provider=body.get("provider", "apple_pay"),
                )
                return self._json(200, {"dpan": tok.dpan, "expiry": body["expiry"]})
            if path == "/wallet/tap":
                # El "wallet" del frontend no tiene Secure Element real,
                # asi que aqui el server hace de SE: firma con la llave del DPAN
                # y procesa la auth. Es solo para demo del flujo end-to-end.
                tok_rec = ISSUER.tsp.get_record(body["dpan"])
                if not tok_rec:
                    return self._json(400, {"error": "DPAN desconocido"})
                nonce = secrets.token_hex(8)
                cryptogram = ISSUER.hsm.compute_token_cryptogram(
                    tok_rec.token.token_key, body["dpan"],
                    int(body["amount_minor"]), nonce,
                )
                req = AuthRequest(
                    pan=body["dpan"],
                    expiry_mmYY=body.get("expiry", ""),
                    cvv=None,
                    amount=Money(int(body["amount_minor"]),
                                 body.get("currency", "MXN")),
                    mcc=body.get("mcc", DEFAULT_MERCHANT.mcc),
                    merchant_id=body.get("merchant_id", DEFAULT_MERCHANT.merchant_id),
                    terminal_id=body.get("terminal_id", DEFAULT_TERMINAL.terminal_id),
                    pos_entry=POSEntryMode.NFC_WALLET,
                    country_iso2=body.get("country", "MX"),
                    dpan=body["dpan"], cryptogram=cryptogram, nonce=nonce,
                )
                out = ISSUER.authorize(req)
                if out.approved and out.txn:
                    ACQ.pending_auths.append(PendingAuth(
                        txn_id=out.txn.txn_id,
                        merchant_id=req.merchant_id,
                        pan_first6=body["dpan"][:6],
                        amount_minor=req.amount.amount_minor,
                        currency=req.amount.currency,
                    ))
                return self._json(200, {
                    "approved": out.approved, "rc": out.rc.value,
                    "message": out.message,
                    "txn_id": out.txn.txn_id if out.txn else None,
                    "auth_code": out.txn.auth_code if out.txn else None,
                    "dpan_used": body["dpan"],
                })
            self._json(404, {"error": "not found"})
        except Exception as e:
            self._json(400, {"error": str(e)})


def main(host: str = "127.0.0.1", port: int = 8765) -> None:
    line = "=" * 64
    print(line)
    print(f"  Payment Card Lab — API + UI en  http://{host}:{port}")
    print(line)
    print(f"  Issuer        : {ISSUER.config.name}  (BIN {ISSUER.config.bin})")
    print(f"  Merchant      : {DEFAULT_MERCHANT.name}  ({DEFAULT_MERCHANT.merchant_id})")
    print(f"  Terminal      : {DEFAULT_TERMINAL.terminal_id}")
    print(line)
    print("  TARJETA LISTA PARA USAR (emitida automaticamente):")
    print(line)
    print(f"  Titular       : {STARTER_HOLDER.full_name}")
    print(f"  PAN           : {STARTER_CARD.pan}")
    print(f"  Vencimiento   : {STARTER_CARD.expiry_mmYY}")
    print(f"  CVV           : {STARTER_CARD.cvv}")
    print(f"  Saldo inicial : ${STARTER_ACCOUNT.posted_minor/100:,.2f} MXN")
    print(line)
    print(f"  >>> Abre en tu browser:  http://{host}:{port}/")
    print(f"      La tarjeta ya aparece cargada. Solo escribe el monto y")
    print(f"      dale 'Cobrar'.")
    print(line)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
