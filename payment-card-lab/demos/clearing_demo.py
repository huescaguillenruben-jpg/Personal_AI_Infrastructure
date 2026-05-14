"""Demo 06: Clearing batch.

Despues de varias autorizaciones, corremos el batch:
captura cada auth, posted_minor del cliente cae, payable del comercio sube.
"""

from __future__ import annotations

from pailab.clearing import ClearingEngine
from pailab.luhn import bin_of

from ._setup import banner, build_world, fmt_money


def run() -> None:
    banner("Demo 06: Clearing batch")
    w = build_world()

    # Tres compras autorizadas (hold).
    for amount in (50_00, 75_00, 30_00):
        rsp = w.terminal.swipe(w.card.pan, w.card.expiry_mmYY,
                               w.card.cvv, amount)
        print(f"swipe {fmt_money(amount)} -> RC={rsp.get('RESPONSE_CODE')}")

    print(f"\nantes del batch:")
    print(f"  posted = {fmt_money(w.account.posted_minor)}")
    print(f"  held   = {fmt_money(w.account.held_minor)}")
    print(f"  merchant payable = {fmt_money(w.merchant.payable_minor)}")
    print(f"  acquirer pending = {len(w.acquirer.pending_auths)}")

    # Correr clearing.
    ce = ClearingEngine(w.acquirer, {bin_of(w.card.pan): w.issuer})
    result = ce.run_batch()
    print(f"\nbatch: {result}")

    print(f"\ndespues del batch:")
    print(f"  posted = {fmt_money(w.account.posted_minor)}")
    print(f"  held   = {fmt_money(w.account.held_minor)}")
    print(f"  merchant payable = {fmt_money(w.merchant.payable_minor)}")


if __name__ == "__main__":
    run()
