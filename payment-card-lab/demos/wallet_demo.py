"""Demo 03: Wallet movil con tokenizacion (DPAN) y tap-to-pay."""

from __future__ import annotations

from pailab.wallet import MobileWallet

from ._setup import banner, build_world, fmt_money


def run() -> None:
    banner("Demo 03: Wallet movil + NFC")
    w = build_world()
    print(f"PAN real:  {w.card.pan}")

    # 1) Agregar tarjeta al wallet -> emite DPAN
    phone = MobileWallet.new(provider="apple_pay")
    dpan = phone.add_card(issuer=w.issuer, pan=w.card.pan,
                          expiry=w.card.expiry_mmYY, cvv=w.card.cvv)
    print(f"DPAN:      {dpan}   (distinto al PAN real)")

    # 2) Tap to pay $150.00
    rsp = phone.tap_to_pay(dpan=dpan, terminal=w.terminal,
                           amount_minor=150_00,
                           expiry_hint=w.card.expiry_mmYY)
    print(f"\nTap NFC $150.00       -> RC={rsp.get('RESPONSE_CODE')} auth={rsp.get('AUTH_CODE')}")
    print(f"  disponible:         {fmt_money(w.account.available_minor())}")

    # 3) Si "pierdes el celular": suspender el DPAN -> tap rechazado
    w.issuer.tsp.suspend(dpan)
    rsp = phone.tap_to_pay(dpan=dpan, terminal=w.terminal,
                           amount_minor=10_00,
                           expiry_hint=w.card.expiry_mmYY)
    print(f"Tap con DPAN suspendido -> RC={rsp.get('RESPONSE_CODE')}")

    # La tarjeta fisica sigue viva:
    rsp = w.terminal.swipe(w.card.pan, w.card.expiry_mmYY, w.card.cvv, 30_00)
    print(f"Swipe tarjeta fisica    -> RC={rsp.get('RESPONSE_CODE')}  (sigue funcionando)")


if __name__ == "__main__":
    run()
