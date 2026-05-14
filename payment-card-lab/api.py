"""HTTP API minimal (stdlib http.server) sobre el laboratorio.

Endpoints:
    GET  /health
    POST /holders                      {full_name, country}
    POST /accounts                     {holder_id, type, initial_deposit_minor, currency}
    POST /cards                        {account_id}
    POST /cards/{pan}/activate
    GET  /accounts/{account_id}
    POST /authorize                    AuthRequest JSON (subset)
    POST /capture                      {txn_id}
    POST /reverse                      {txn_id}
    POST /wallet/provision             {pan, expiry, cvv, device_id, provider}
    POST /wallet/tap                   {dpan, amount_minor, nonce, cryptogram, ...}

NO escuchar en red publica; uso local solamente.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pailab.acquirer import Acquirer
from pailab.crypto import HSM
from pailab.errors import RC
from pailab.issuer import Issuer, IssuerConfig
from pailab.logging_utils import configure_logging, mask_pan
from pailab.models import AccountType, AuthRequest, Money, POSEntryMode
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
DEFAULT_MERCHANT = ACQ.onboard_merchant("ApiMerchant", mcc="5812")
DEFAULT_TERMINAL = Terminal.deploy(ACQ, DEFAULT_MERCHANT)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, format, *args):
        # Silenciar el log default; lo manejamos via pailab.
        pass

    # ----- rutas ------------------------------------------------------
    def do_GET(self):
        try:
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if self.path.startswith("/accounts/"):
                acc_id = self.path.split("/")[-1]
                acc = ISSUER.ledger.get(acc_id)
                return self._send(200, {
                    "account_id": acc.account_id,
                    "type": acc.account_type.value,
                    "currency": acc.currency,
                    "posted_minor": acc.posted_minor,
                    "held_minor": acc.held_minor,
                    "available_minor": acc.available_minor(),
                })
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_POST(self):
        try:
            body = self._read()
            if self.path == "/holders":
                h = ISSUER.register_holder(body["full_name"],
                                           body.get("country", "MX"))
                return self._send(200, {"holder_id": h.holder_id})
            if self.path == "/accounts":
                holder = ISSUER.holders[body["holder_id"]]
                acc = ISSUER.open_account(
                    holder, AccountType(body.get("type", "checking")),
                    initial_deposit=Money(int(body.get("initial_deposit_minor", 0)),
                                          body.get("currency", "MXN")),
                )
                return self._send(200, {"account_id": acc.account_id})
            if self.path == "/cards":
                acc = ISSUER.ledger.get(body["account_id"])
                card = ISSUER.issue_card(acc)
                ISSUER.activate_card(card.pan)
                return self._send(200, {
                    "pan": card.pan, "expiry": card.expiry_mmYY,
                    "cvv": card.cvv, "pan_masked": mask_pan(card.pan),
                })
            if self.path == "/authorize":
                pos = POSEntryMode(body.get("pos_entry", "swipe"))
                req = AuthRequest(
                    pan=body["pan"],
                    expiry_mmYY=body["expiry"],
                    cvv=body.get("cvv"),
                    amount=Money(int(body["amount_minor"]),
                                 body.get("currency", "MXN")),
                    mcc=body.get("mcc", "5812"),
                    merchant_id=body.get("merchant_id", DEFAULT_MERCHANT.merchant_id),
                    terminal_id=body.get("terminal_id", DEFAULT_TERMINAL.terminal_id),
                    pos_entry=pos,
                    country_iso2=body.get("country", "MX"),
                )
                out = ISSUER.authorize(req)
                return self._send(200, {
                    "approved": out.approved,
                    "rc": out.rc.value,
                    "message": out.message,
                    "txn_id": out.txn.txn_id if out.txn else None,
                    "auth_code": out.txn.auth_code if out.txn else None,
                    "threeds_challenge": out.threeds_challenge,
                })
            if self.path == "/capture":
                ISSUER.capture(body["txn_id"])
                return self._send(200, {"ok": True})
            if self.path == "/reverse":
                ISSUER.reverse(body["txn_id"])
                return self._send(200, {"ok": True})
            if self.path == "/wallet/provision":
                tok = ISSUER.provision_token(
                    pan=body["pan"], expiry_mmYY=body["expiry"],
                    cvv=body["cvv"],
                    device_id=body["device_id"],
                    wallet_provider=body.get("provider", "apple_pay"),
                )
                return self._send(200, {"dpan": tok.dpan})
            if self.path == "/wallet/tap":
                req = AuthRequest(
                    pan=body["dpan"], expiry_mmYY=body.get("expiry", ""),
                    cvv=None,
                    amount=Money(int(body["amount_minor"]),
                                 body.get("currency", "MXN")),
                    mcc=body.get("mcc", "5812"),
                    merchant_id=body.get("merchant_id", DEFAULT_MERCHANT.merchant_id),
                    terminal_id=body.get("terminal_id", DEFAULT_TERMINAL.terminal_id),
                    pos_entry=POSEntryMode.NFC_WALLET,
                    country_iso2=body.get("country", "MX"),
                    dpan=body["dpan"], cryptogram=body["cryptogram"],
                    nonce=body["nonce"],
                )
                out = ISSUER.authorize(req)
                return self._send(200, {
                    "approved": out.approved, "rc": out.rc.value,
                    "txn_id": out.txn.txn_id if out.txn else None,
                })
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(400, {"error": str(e)})


def main(host: str = "127.0.0.1", port: int = 8765) -> None:
    print(f"Lab API en http://{host}:{port}  (solo local, sin TLS)")
    print(f"  emisor BIN = {ISSUER.config.bin}")
    print(f"  merchant   = {DEFAULT_MERCHANT.merchant_id}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
