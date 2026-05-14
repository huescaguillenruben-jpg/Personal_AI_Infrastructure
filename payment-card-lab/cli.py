"""CLI del laboratorio: corre cada demo individual o todos."""

from __future__ import annotations

import argparse
import logging

from pailab.logging_utils import configure_logging


DEMOS = {
    "basic":    "demos.basic",
    "emv":      "demos.emv",
    "wallet":   "demos.wallet_demo",
    "threeds":  "demos.threeds",
    "fraud":    "demos.fraud_demo",
    "clearing": "demos.clearing_demo",
    "e2e":      "demos.e2e",
    "stripe":   "demos.compare_stripe",
    "stripe-real": "demos.stripe_real",
}


def main() -> int:
    p = argparse.ArgumentParser(description="Payment Card Lab CLI")
    p.add_argument("demo", choices=list(DEMOS.keys()) + ["all"],
                   help="Demo a correr")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Logs INFO de pailab")
    args = p.parse_args()
    configure_logging(level=logging.INFO if args.verbose else logging.WARNING)

    import importlib
    targets = list(DEMOS) if args.demo == "all" else [args.demo]
    for name in targets:
        mod = importlib.import_module(DEMOS[name])
        mod.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
