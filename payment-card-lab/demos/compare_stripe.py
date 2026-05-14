"""Demo 08: Comparacion lab vs. Stripe sandbox.

Responde la pregunta: "que cambia entre un PAN del lab y un PAN de
prueba de Stripe que SI 'funciona' contra Stripe?"

Spoiler: la tecnologia es la misma. Lo unico que cambia es que el PAN
de prueba esta registrado en la base de datos de Stripe (lado merchant)
y nuestro PAN del lab esta registrado en BancoLab (nuestra base local).

Que cada uno acepte solo sus propios PAN es por diseno.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from pailab.acquirer import Acquirer
from pailab.issuer import Issuer, IssuerConfig
from pailab.luhn import luhn_valid
from pailab.models import AccountType, Money
from pailab.network import CardNetwork
from pailab.terminal import Terminal


# --- Numeros de prueba publicados oficialmente por Stripe ---
# Fuente: https://stripe.com/docs/testing
# Solo "funcionan" con secret keys de tipo sk_test_*.
STRIPE_TEST_PANS = [
    ("4242424242424242", "visa", "approved"),
    ("4000000000000002", "visa", "declined (generic)"),
    ("4000000000009995", "visa", "declined (insufficient_funds)"),
    ("4000002500003155", "visa", "requires 3DS auth"),
    ("5555555555554444", "mastercard", "approved"),
    ("378282246310005",  "amex",       "approved"),
]


def section(t: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {t}")
    print("=" * 64)


# ---------------------------------------------------------------------
# 1. Demuestra que NUESTRO PAN funciona en el lab
# ---------------------------------------------------------------------
def lab_demo() -> tuple[str, str, str]:
    section("1. PAN generado en el lab -> autoriza contra BancoLab")
    iss = Issuer(IssuerConfig(name="BancoLab"))
    acq = Acquirer("AcqLab")
    net = CardNetwork("LabNet")
    net.register_issuer(iss.config.bin, iss)
    net.register_tsp(iss.tsp)
    acq.network = net
    merchant = acq.onboard_merchant("CafeDemo", mcc="5812")
    term = Terminal.deploy(acq, merchant)

    holder = iss.register_holder("Ruben Huesca")
    acc = iss.open_account(holder, AccountType.CHECKING,
                           initial_deposit=Money(10_000_00))
    card = iss.issue_card(acc)
    iss.activate_card(card.pan)

    print(f"  PAN          : {card.pan}")
    print(f"  Expiry       : {card.expiry_mmYY}    CVV: {card.cvv}")
    print(f"  Luhn valido? : {luhn_valid(card.pan)}")
    print(f"  Registrado en: BancoLab.cards[{card.pan}]  <- nuestra base")
    rsp = term.swipe(card.pan, card.expiry_mmYY, card.cvv, 50_000_00)
    print(f"  Cargo $500.00-> RC={rsp.get('RESPONSE_CODE')} auth={rsp.get('AUTH_CODE')}")
    return card.pan, card.expiry_mmYY, card.cvv


# ---------------------------------------------------------------------
# 2. Demuestra que el PAN del lab NO le sirve a Stripe
# ---------------------------------------------------------------------
def call_stripe_with_pan(pan: str, secret_key: str) -> tuple[int, dict]:
    """POST /v1/payment_methods a Stripe usando llaves de prueba.

    Stripe responde:
      200 + payment_method id  -> el PAN esta en su base de pruebas
      402 + card_declined      -> PAN reconocido pero rechazado a proposito
      400 + invalid_number     -> PAN NO esta registrado en Stripe
      401                      -> secret_key incorrecta o ausente
    """
    data = urllib.parse.urlencode({
        "type": "card",
        "card[number]": pan,
        "card[exp_month]": "12",
        "card[exp_year]": "2030",
        "card[cvc]": "123",
    }).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/payment_methods",
        data=data,
        method="POST",
        headers={"Authorization": f"Bearer {secret_key}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def stripe_demo(lab_pan: str, lab_exp: str, lab_cvv: str) -> None:
    key = os.environ.get("STRIPE_TEST_KEY", "sk_test_FAKE_PLACEHOLDER")

    section("2. El mismo PAN del lab -> contra api.stripe.com (test mode)")
    print(f"  Mandamos {lab_pan} a Stripe...")
    code, body = call_stripe_with_pan(lab_pan, key)
    print(f"  HTTP {code}")
    err = body.get("error", {})
    if code == 401:
        print(f"  -> Stripe dice: API key invalida ({err.get('message', '')[:80]}).")
        print(f"  (Esto es esperado: este script no tiene sk_test_ real.")
        print(f"   Mete tu llave de prueba en STRIPE_TEST_KEY si quieres ver")
        print(f"   el resultado real con tu cuenta de Stripe.)")
    elif code == 400 and err.get("code") == "invalid_number":
        print(f"  -> Stripe dice: 'Your card number is incorrect.'")
        print(f"     (PASA Luhn pero NO esta en la base de prueba de Stripe)")
    else:
        print(f"  -> respuesta inesperada: {body}")

    section("3. PANs de prueba PUBLICADOS por Stripe -> mismo endpoint")
    for pan, brand, expected in STRIPE_TEST_PANS:
        code, body = call_stripe_with_pan(pan, key)
        err = body.get("error", {})
        tag = f"HTTP {code}"
        if code == 200:
            tag += f"  pm={body.get('id')}"
        elif code == 401:
            tag += "  (necesita sk_test_ real)"
        elif err:
            tag += f"  {err.get('code','')} {err.get('message','')[:50]}"
        print(f"  {pan:18s}  {brand:11s}  {expected:32s}  -> {tag}")


# ---------------------------------------------------------------------
# 3. La explicacion
# ---------------------------------------------------------------------
def explain() -> None:
    section("4. Que cambia que un PAN 'funcione' contra un sistema?")
    print("""
  Tecnicamente ambos PAN (el del lab y el 4242 4242 4242 4242):
    * Tienen 16 digitos
    * Pasan el algoritmo de Luhn (publico, no autentica nada)
    * Llevan un BIN al inicio (4xx... -> familia Visa)

  La unica diferencia es:

  +-----------------+-----------------------------------------------+
  | PAN del lab     | esta en BancoLab.cards en RAM de tu proceso   |
  |                 | -> "funciona" mientras corre el lab           |
  +-----------------+-----------------------------------------------+
  | 4242 4242 4242  | esta en la base de TEST de Stripe en su nube  |
  |  4242 (Stripe)  | -> "funciona" contra api.stripe.com sk_test_  |
  +-----------------+-----------------------------------------------+
  | tarjeta real    | esta en la base de PRODUCCION del banco       |
  | de tu cartera   | emisor, respaldada por dinero real            |
  |                 | -> funciona en cualquier comercio que la      |
  |                 |   marca rute al emisor correcto                |
  +-----------------+-----------------------------------------------+

  Que cambia para que algo "funcione":
    no es la tecnologia ni el numero -> es estar registrado en una
    base de datos que el sistema con el que hablas considera autoridad.

  Por eso:
    * No puedes inventar un PAN que funcione contra Stripe (sin llave).
    * No puedes inventar un PAN que funcione contra Visa/Mastercard.
    * El lab y Stripe test mode existen para que aprendas SIN tocar
      dinero real ni intentar engañar a un sistema ajeno.

  Para obtener tu propia llave sk_test_:
    1. crea cuenta gratis en https://dashboard.stripe.com/register
    2. Developers -> API keys -> 'Reveal test key'
    3. export STRIPE_TEST_KEY=sk_test_...
    4. python3 -m demos.compare_stripe
    -> ahora los PAN de Stripe daran HTTP 200 y veras un payment_method real
    (pero sin cobro de verdad, porque tu cuenta esta en test mode).
""")


def run() -> None:
    pan, exp, cvv = lab_demo()
    stripe_demo(pan, exp, cvv)
    explain()


if __name__ == "__main__":
    run()
