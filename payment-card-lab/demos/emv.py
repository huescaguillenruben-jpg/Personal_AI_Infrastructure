"""Demo 02: Compra con chip EMV (ARQC).

El terminal genera un UN (Unpredictable Number) y se lo pasa al chip.
El chip computa el ARQC con su llave derivada (MK_AC -> SK_AC). El
issuer verifica el ARQC con su HSM y el contador ATC para detectar replay.
"""

from __future__ import annotations

from ._setup import banner, build_world, fmt_money


def run() -> None:
    banner("Demo 02: EMV chip (ARQC)")
    w = build_world()
    # En el lab usamos el MISMO HSM del emisor como "chip" porque ambos
    # comparten la jerarquia de llaves. En la realidad la llave maestra
    # del emisor entrega la MK_AC durante la personalizacion de la tarjeta.
    chip_hsm = w.issuer.hsm
    atc = 1

    # Compra normal
    rsp = w.terminal.chip(w.card.pan, w.card.expiry_mmYY, 250_00,
                          card_hsm=chip_hsm, atc=atc, psn=w.card.card_seq_num)
    print(f"EMV chip $250.00      -> RC={rsp.get('RESPONSE_CODE')}  ATC={atc}")

    # Intento de replay: mismo ATC -> falla
    rsp = w.terminal.chip(w.card.pan, w.card.expiry_mmYY, 250_00,
                          card_hsm=chip_hsm, atc=atc, psn=w.card.card_seq_num)
    print(f"EMV chip replay ATC={atc} -> RC={rsp.get('RESPONSE_CODE')}")

    # Siguiente compra con ATC=2 -> aprobada
    atc = 2
    rsp = w.terminal.chip(w.card.pan, w.card.expiry_mmYY, 75_00,
                          card_hsm=chip_hsm, atc=atc, psn=w.card.card_seq_num)
    print(f"EMV chip $75.00       -> RC={rsp.get('RESPONSE_CODE')}  ATC={atc}")

    print(f"\nSaldo disponible: {fmt_money(w.account.available_minor())}")


if __name__ == "__main__":
    run()
