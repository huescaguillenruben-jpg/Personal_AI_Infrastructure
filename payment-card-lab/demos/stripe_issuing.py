"""Demo 10: Stripe Issuing - EMITE TU PROPIA tarjeta virtual.

Esto contesta la pregunta "podemos crear nuestro propio PAN que funcione?":
si, contra Stripe sandbox. Stripe te emite un PAN real (con BIN suyo, no
inventado) y un CVV; el PAN queda en la base de Stripe asociado a tu
cuenta de prueba.

Flujo:
    1. Cardholder.create(...)              -> persona detras de la tarjeta
    2. Card.create(type='virtual', ...)    -> emite el PAN
    3. Card.retrieve(expand=['number','cvc']) -> ver los datos sensibles
    4. test_helpers.issuing.Authorization.create(card=...)  -> simular cobro
    5. test_helpers.issuing.Authorization.capture(...)      -> capturarlo

Requiere:
    pip install stripe
    export STRIPE_TEST_KEY=sk_test_...
    Stripe Issuing habilitado en tu cuenta de prueba (gratis en signup
    para US, UK, EU. Mexico aun no esta GA — usa direccion US en test).
"""

from __future__ import annotations

import os
import sys


def section(t: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {t}")
    print("=" * 64)


def run() -> None:
    try:
        import stripe
    except ImportError:
        print("Falta: pip3 install stripe")
        return

    key = os.environ.get("STRIPE_TEST_KEY")
    if not key:
        section("STRIPE_TEST_KEY no exportada")
        print("""
  Pasos:
    1. Cuenta en https://dashboard.stripe.com/register
    2. Developers -> API keys -> Reveal test key
    3. export STRIPE_TEST_KEY=sk_test_...
    4. python3 cli.py stripe-issuing

  Stripe Issuing en TEST mode esta disponible automaticamente en
  cuentas nuevas (al menos para direcciones US). No tienes que aplicar
  para test; solo para produccion.
""")
        return
    if not key.startswith("sk_test_"):
        print("Solo sk_test_. Negativa absoluta a usar sk_live_ aqui.")
        sys.exit(2)
    stripe.api_key = key
    stripe.api_version = "2024-06-20"

    # -------------------------------------------------------------------
    # 1. Crear el Cardholder (la persona)
    # -------------------------------------------------------------------
    section("1. Crear Cardholder (la persona dueña de la tarjeta)")
    try:
        ch = stripe.issuing.Cardholder.create(
            type="individual",
            name="Ruben Huesca",
            email="ruben.test@example.com",
            phone_number="+15551234567",   # E.164
            billing={
                "address": {
                    "line1": "1234 Market St",
                    "city": "San Francisco",
                    "state": "CA",
                    "country": "US",         # test usa USA por default
                    "postal_code": "94103",
                },
            },
        )
        print(f"  cardholder_id: {ch.id}")
        print(f"  nombre:        {ch.name}")
        print(f"  status:        {ch.status}")
    except stripe.error.InvalidRequestError as e:
        msg = str(e)
        if "issuing" in msg.lower() and ("not been enabled" in msg.lower()
                                         or "capability" in msg.lower()):
            section("Stripe Issuing NO esta habilitado en tu cuenta de prueba")
            print("""
  Esto pasa si tu cuenta de Stripe es muy nueva o esta en una region donde
  Issuing aun no es self-serve. Soluciones:

    a) En https://dashboard.stripe.com/test/issuing/overview
       da click en "Get started with Issuing" / "Activate".
       Es instantaneo en test mode para US/UK/EU.

    b) Crea una segunda cuenta de Stripe con direccion US y usala
       solo para experimentar con Issuing.

  Error tal cual de Stripe:
    {}
""".format(msg[:200]))
            return
        print(f"  Error de Stripe al crear cardholder: {msg[:200]}")
        return
    except stripe.error.AuthenticationError:
        print("  La llave sk_test_ es invalida. Verifica STRIPE_TEST_KEY.")
        return
    except stripe.error.APIConnectionError as e:
        print(f"  No alcanza api.stripe.com (red o SSL): {str(e)[:160]}")
        return
    except Exception as e:
        print(f"  Error inesperado ({type(e).__name__}): {str(e)[:200]}")
        return

    # -------------------------------------------------------------------
    # 2. Emitir la tarjeta virtual
    # -------------------------------------------------------------------
    section("2. Emitir tarjeta virtual con ese Cardholder")
    card = stripe.issuing.Card.create(
        cardholder=ch.id,
        currency="usd",
        type="virtual",
        status="active",
    )
    print(f"  card_id:       {card.id}")
    print(f"  brand:         {card.brand}")
    print(f"  last4:         {card.last4}")
    print(f"  exp_month:     {card.exp_month}")
    print(f"  exp_year:      {card.exp_year}")
    print(f"  status:        {card.status}")
    print(f"  type:          {card.type}")
    print(f"  currency:      {card.currency}")

    # -------------------------------------------------------------------
    # 3. Ver el PAN completo (solo se puede en test, o via Stripe.js en prod)
    # -------------------------------------------------------------------
    section("3. Recuperar PAN + CVV completos (solo test mode)")
    try:
        details = stripe.issuing.Card.retrieve(
            card.id,
            expand=["number", "cvc"],
        )
        print(f"  PAN:           {details.number}")
        print(f"  CVV:           {details.cvc}")
        print(f"  Vencimiento:   {details.exp_month:02d}/{str(details.exp_year)[2:]}")
        print()
        print("  ^^ ESTE es 'tu propio PAN'. Lo emitio Stripe, esta en su")
        print("     base, y responde contra api.stripe.com sk_test_.")
        print("     En produccion: stripe.js o iOS/Android SDK lo muestra")
        print("     directo al cardholder, sin que tu backend lo vea (PCI).")
    except Exception as e:
        print(f"  No pude recuperar el PAN completo ({type(e).__name__}):")
        print(f"    {str(e)[:200]}")
        print(f"  Tip: en algunas regiones requiere otra ruta. last4 si funciono: {card.last4}")
        details = card

    # -------------------------------------------------------------------
    # 4. Simular una autorizacion contra esta tarjeta (test helpers)
    # -------------------------------------------------------------------
    section("4. Simular un cobro de USD $25 contra TU tarjeta")
    # En stripe-python v15+ los test helpers viven en StripeClient.v1.test_helpers
    client = stripe.StripeClient(key)
    try:
        auth = client.v1.test_helpers.issuing.authorizations.create(
            params={
                "card": card.id,
                "amount": 2500,
                "currency": "usd",
                "merchant_data": {
                    "category": "computer_software_stores",
                    "city": "San Francisco",
                    "country": "US",
                    "name": "Software Shop Test",
                    "network_id": "1234567890",
                    "postal_code": "94103",
                    "state": "CA",
                },
            }
        )
        print(f"  authorization_id: {auth.id}")
        print(f"  status:           {auth.status}")
        print(f"  amount:           ${auth.amount/100:.2f} {auth.currency}")
        print(f"  approved:         {auth.approved}")
        print(f"  merchant:         {auth.merchant_data.name}")
        if auth.status == "pending":
            print()
            print("  -> capturando (la autorizacion pasa a 'closed')...")
            captured = client.v1.test_helpers.issuing.authorizations.capture(auth.id)
            print(f"     status final: {captured.status}")
    except Exception as e:
        print(f"  Error al simular auth ({type(e).__name__}):")
        print(f"    {str(e)[:200]}")

    # -------------------------------------------------------------------
    # 5. Listar las tarjetas y autorizaciones del cardholder
    # -------------------------------------------------------------------
    section("5. Listar todas las tarjetas y autorizaciones del cardholder")
    cards = stripe.issuing.Card.list(cardholder=ch.id, limit=5)
    for c in cards.data:
        print(f"  card {c.id}  last4={c.last4}  exp={c.exp_month:02d}/{c.exp_year}  status={c.status}")
    auths = stripe.issuing.Authorization.list(card=card.id, limit=5)
    for a in auths.data:
        print(f"  auth {a.id}  ${a.amount/100:.2f}  status={a.status}  merchant={a.merchant_data.name}")

    section("Conclusion")
    print("""
  Lo que paso aqui:
    * Tu app llamo a Stripe Issuing y emitio un PAN nuevo.
    * El PAN existe en la base de TEST de Stripe, asociado a tu cuenta.
    * Stripe firma su propio criptograma para ese PAN (TSP integrado).
    * Cualquier cargo contra ese PAN con sk_test_ va contra esa base.

  Diferencia con `python3 cli.py basic`:
    * En el lab tu eras emisor (BancoLab.cards[pan] = ...).
    * En Issuing tu pediste a Stripe que sea el emisor por ti.
    * Conceptualmente: misma operacion, diferente quien controla la
      base de PANs.

  Para llevarlo a produccion:
    1. Activa Stripe Issuing live (KYC, fondeo de la cuenta).
    2. Pasa de sk_test_ a sk_live_.
    3. Los PANs emitidos ahora aceptan cargos reales en cualquier
       comercio del mundo, y los fondos salen de tu cuenta de Stripe.
    4. En Mexico Issuing aun no es GA; usar EUA / UK / EU como bookkeeping
       country o esperar a la apertura LATAM (Pomelo es la alternativa
       latam-first).
""")


if __name__ == "__main__":
    run()
