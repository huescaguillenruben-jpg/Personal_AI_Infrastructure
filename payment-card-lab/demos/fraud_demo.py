"""Demo 05: Reglas antifraude.

  - velocidad: muchas compras seguidas
  - geografia: terminal en otro pais que el "home"
  - MCC riesgoso
"""

from __future__ import annotations

from pailab.acquirer import Acquirer
from pailab.network import CardNetwork
from pailab.terminal import Terminal

from ._setup import banner, build_world


def run() -> None:
    banner("Demo 05: Reglas antifraude")
    w = build_world()

    # --- velocidad: 6 compras en menos de 60s -> la 6a se cae
    print("\n[velocidad] 6 compras rapidas:")
    for i in range(6):
        rsp = w.terminal.swipe(w.card.pan, w.card.expiry_mmYY,
                               w.card.cvv, 10_00)
        print(f"  intento {i+1} -> RC={rsp.get('RESPONSE_CODE')}")

    # --- geografia: nuevo adquirente en US, nueva terminal
    print("\n[geo] mismo PAN, terminal en US:")
    us_acq = Acquirer("AcqUSA", country_iso2="US", currency="MXN")
    us_acq.network = w.network
    us_merchant = us_acq.onboard_merchant("CafeUSA", mcc="5812")
    us_terminal = Terminal.deploy(us_acq, us_merchant)
    rsp = us_terminal.swipe(w.card.pan, w.card.expiry_mmYY, w.card.cvv, 20_00)
    print(f"  RC={rsp.get('RESPONSE_CODE')}  (suma puntos por geo)")

    # --- MCC riesgoso 7995 (apuestas)
    print("\n[mcc] apuestas (7995):")
    bet_merchant = w.acquirer.onboard_merchant("BetSitio", mcc="7995")
    bet_terminal = Terminal.deploy(w.acquirer, bet_merchant)
    rsp = bet_terminal.ecommerce(w.card.pan, w.card.expiry_mmYY,
                                 w.card.cvv, 200_00)
    print(f"  RC={rsp.get('RESPONSE_CODE')}")


if __name__ == "__main__":
    run()
