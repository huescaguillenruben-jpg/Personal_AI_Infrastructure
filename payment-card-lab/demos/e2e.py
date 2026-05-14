"""Demo 07: end-to-end.

Junta todos los componentes en una sola corrida:
    emision -> swipe -> EMV chip -> e-commerce con 3DS -> wallet NFC ->
    intento de fraude -> reverso -> clearing -> reporte final.
"""

from __future__ import annotations

import json

from pailab.clearing import ClearingEngine
from pailab.luhn import bin_of
from pailab.wallet import MobileWallet

from ._setup import banner, build_world, fmt_money


def run() -> None:
    banner("Demo END-TO-END")
    w = build_world(initial_deposit_minor=10_000_00)
    iss, acq = w.issuer, w.acquirer

    print(f"\nEmision:")
    print(f"  Titular   : {w.holder.full_name}")
    print(f"  Cuenta    : {w.account.account_id}")
    print(f"  PAN       : {w.card.pan}")
    print(f"  Expiry    : {w.card.expiry_mmYY}    CVV: {w.card.cvv}")
    print(f"  Saldo     : {fmt_money(w.account.posted_minor)}")

    # 1) Swipe
    rsp = w.terminal.swipe(w.card.pan, w.card.expiry_mmYY, w.card.cvv, 120_00)
    print(f"\n[1] Swipe $120.00       -> RC={rsp.get('RESPONSE_CODE')} auth={rsp.get('AUTH_CODE')}")

    # 2) Chip EMV
    rsp = w.terminal.chip(w.card.pan, w.card.expiry_mmYY, 250_00,
                          card_hsm=iss.hsm, atc=1, psn=w.card.card_seq_num)
    print(f"[2] EMV chip $250.00    -> RC={rsp.get('RESPONSE_CODE')} auth={rsp.get('AUTH_CODE')}")

    # 3) E-commerce con 3DS
    rsp = w.terminal.ecommerce(w.card.pan, w.card.expiry_mmYY, w.card.cvv, 2_500_00)
    rc = rsp.get("RESPONSE_CODE")
    ecom = json.loads(rsp.get("ECOM_DATA"))
    cid, otp = ecom["challenge_id"], ecom["otp_demo"]
    ver = iss.acs.verify(cid, otp)
    rsp = w.terminal.ecommerce(w.card.pan, w.card.expiry_mmYY, w.card.cvv, 2_500_00,
                               cavv=ver.cavv, cavv_cid=cid)
    print(f"[3] CNP $2,500 + 3DS    -> RC={rsp.get('RESPONSE_CODE')} auth={rsp.get('AUTH_CODE')}")

    # 4) Wallet NFC
    phone = MobileWallet.new("apple_pay")
    dpan = phone.add_card(issuer=iss, pan=w.card.pan,
                          expiry=w.card.expiry_mmYY, cvv=w.card.cvv)
    rsp = phone.tap_to_pay(dpan=dpan, terminal=w.terminal, amount_minor=80_00,
                           expiry_hint=w.card.expiry_mmYY)
    print(f"[4] NFC wallet $80.00   -> RC={rsp.get('RESPONSE_CODE')} auth={rsp.get('AUTH_CODE')}")

    # 5) Intento de tap con criptograma falso -> rechazado
    rsp = w.terminal.nfc_wallet(dpan=dpan, expiry=w.card.expiry_mmYY,
                                amount_minor=80_00,
                                cryptogram="deadbeef" * 4, nonce="abc")
    print(f"[5] NFC con crypto falso-> RC={rsp.get('RESPONSE_CODE')}")

    # 6) Reverso de la transaccion swipe (txn_id = AUTH_CODE? -> usamos lista interna)
    last_txn = next(iter(reversed(list(iss.transactions.values()))))
    # tomar la primera APROBADA autorizada (swipe)
    swipe_txn = next(t for t in iss.transactions.values()
                     if t.state.value == "authorized")
    iss.reverse(swipe_txn.txn_id)
    print(f"[6] Reverso swipe       -> txn={swipe_txn.txn_id}")

    # 7) Clearing
    ce = ClearingEngine(acq, {bin_of(w.card.pan): iss})
    result = ce.run_batch()
    print(f"[7] Clearing batch      -> {result}")

    # 8) Reporte
    print(f"\nReporte final:")
    print(f"  posted (gastado real) = {fmt_money(w.account.posted_minor)}")
    print(f"  available             = {fmt_money(w.account.available_minor())}")
    print(f"  held                  = {fmt_money(w.account.held_minor)}")
    print(f"  merchant payable      = {fmt_money(w.merchant.payable_minor)}")
    print(f"  transacciones         = {len(iss.transactions)}")
    print(f"  DPANs activos         = {len(iss.tsp.tokens_of(w.card.pan))}")


if __name__ == "__main__":
    run()
