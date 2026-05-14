"""Demo 01: compra basica banda magnetica (swipe), PAN+CVV."""

from __future__ import annotations

from ._setup import banner, build_world, fmt_money


def run() -> None:
    banner("Demo 01: Swipe (banda magnetica)")
    w = build_world(initial_deposit_minor=500_00)   # $500
    print(f"PAN={w.card.pan}  expiry={w.card.expiry_mmYY}  cvv={w.card.cvv}")
    print(f"Saldo inicial: {fmt_money(w.account.posted_minor)}")

    # Compra $120.00 -> aprobada
    rsp = w.terminal.swipe(w.card.pan, w.card.expiry_mmYY, w.card.cvv, 120_00)
    print(f"\nCompra $120.00      -> RC={rsp.get('RESPONSE_CODE')} auth={rsp.get('AUTH_CODE')}")
    print(f"  disponible:       {fmt_money(w.account.available_minor())}  held={fmt_money(w.account.held_minor)}")

    # Compra con CVV incorrecto -> 82
    rsp = w.terminal.swipe(w.card.pan, w.card.expiry_mmYY, "000", 50_00)
    print(f"Compra CVV mal      -> RC={rsp.get('RESPONSE_CODE')}")

    # Compra de $1,000 con $380 disponibles -> 51 fondos insuficientes
    rsp = w.terminal.swipe(w.card.pan, w.card.expiry_mmYY, w.card.cvv, 1_000_00)
    print(f"Compra sin fondos   -> RC={rsp.get('RESPONSE_CODE')}")


if __name__ == "__main__":
    run()
