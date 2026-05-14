"""Helpers compartidos por los demos: construye un mundo basico."""

from __future__ import annotations

from dataclasses import dataclass

from pailab.acquirer import Acquirer, Merchant
from pailab.issuer import Issuer, IssuerConfig
from pailab.models import AccountType, Money
from pailab.network import CardNetwork
from pailab.terminal import Terminal
from pailab.tsp import TSP
from pailab.wallet import MobileWallet


@dataclass
class World:
    issuer: Issuer
    acquirer: Acquirer
    network: CardNetwork
    terminal: Terminal
    merchant: Merchant
    tsp: TSP


def build_world(*, initial_deposit_minor: int = 50_000_00,
                bin_prefix: str = "453219") -> World:
    """Crea un emisor con saldo, un comercio y una terminal lista."""
    tsp = TSP("LabTSP")
    issuer = Issuer(IssuerConfig(name="BancoLab", bin=bin_prefix), tsp=tsp)
    acq = Acquirer("AcqLab")
    net = CardNetwork("LabNet")
    net.register_issuer(bin_prefix, issuer)
    net.register_tsp(tsp)
    acq.network = net

    merchant = acq.onboard_merchant("CafeDemo", mcc="5812")
    terminal = Terminal.deploy(acq, merchant)

    # Cuenta + tarjeta + activacion + saldo inicial.
    holder = issuer.register_holder("Ruben Huesca")
    acc = issuer.open_account(
        holder, AccountType.CHECKING,
        initial_deposit=Money(initial_deposit_minor, "MXN"),
    )
    card = issuer.issue_card(acc)
    issuer.activate_card(card.pan)

    # Exponemos la tarjeta y la cuenta como atributos del world.
    world = World(issuer=issuer, acquirer=acq, network=net,
                  terminal=terminal, merchant=merchant, tsp=tsp)
    world.holder = holder       # type: ignore[attr-defined]
    world.account = acc         # type: ignore[attr-defined]
    world.card = card           # type: ignore[attr-defined]
    return world


def fmt_money(amount_minor: int, currency: str = "MXN") -> str:
    return f"${amount_minor/100:,.2f} {currency}"


def banner(title: str) -> None:
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)
