"""Punto de entrada rapido del laboratorio.

Corre un end-to-end demo: emisor + adquirente + red + comercio + wallet,
con autorizaciones EMV, e-commerce con 3DS, NFC tokenizada, fraude
declinado y clearing en batch.

Para demos individuales mas chicas:
    python3 demos/01_basic.py
    python3 demos/02_emv_chip.py
    python3 demos/03_wallet.py
    python3 demos/04_3ds.py
    python3 demos/05_fraud.py
    python3 demos/06_clearing.py
    python3 demos/07_end_to_end.py
"""

from __future__ import annotations

import logging

from pailab.logging_utils import configure_logging
import demos


def main() -> None:
    configure_logging(level=logging.WARNING)   # silenciar info en el end-to-end
    from demos import e2e
    e2e.run()


if __name__ == "__main__":
    main()
