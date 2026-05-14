"""Helper compartido por los tests: arma un mundo minimo."""

from pailab.acquirer import Acquirer
from pailab.issuer import Issuer, IssuerConfig
from pailab.models import AccountType, Money
from pailab.network import CardNetwork
from pailab.terminal import Terminal


def make_world(deposit_minor: int = 1_000_00):
    iss = Issuer(IssuerConfig(name="Test"))
    acq = Acquirer("AcqT")
    net = CardNetwork("Net")
    net.register_issuer(iss.config.bin, iss)
    net.register_tsp(iss.tsp)
    acq.network = net
    merchant = acq.onboard_merchant("M", "5812")
    term = Terminal.deploy(acq, merchant)
    holder = iss.register_holder("Test")
    acc = iss.open_account(holder, AccountType.CHECKING,
                           initial_deposit=Money(deposit_minor))
    card = iss.issue_card(acc)
    iss.activate_card(card.pan)
    return iss, acq, term, holder, acc, card
