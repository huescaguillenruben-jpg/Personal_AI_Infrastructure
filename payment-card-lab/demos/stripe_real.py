"""Demo 09: Cliente Stripe real en sandbox (test mode).

Requiere:
    pip install stripe
    export STRIPE_TEST_KEY=sk_test_...   # de https://dashboard.stripe.com

Si no esta la llave, el demo te muestra que SE haria sin hacer la llamada.

Flujo que ejecuta:
    1. Crea un Customer
    2. Adjunta un PaymentMethod con un PAN de prueba
    3. Crea un PaymentIntent por un monto
    4. Confirma el PaymentIntent
    5. Si el PAN exige 3DS, muestra el next_action y como manejarlo
    6. Imprime el balance transaction (con el cargo simulado)
"""

from __future__ import annotations

import os
import sys


# PANs de prueba de Stripe que cambian el comportamiento del cargo.
# Fuente oficial: https://docs.stripe.com/testing
SCENARIOS = [
    ("approved",     "4242424242424242", "Visa, aprobada inmediato"),
    ("declined",     "4000000000000002", "Generic decline"),
    ("nofunds",      "4000000000009995", "Insufficient funds"),
    ("requires_3ds", "4000002500003155", "Authentication required (3DS)"),
    ("stolen",       "4000000000009979", "Stolen card"),
    ("expired",      "4000000000000069", "Expired card"),
]


def section(t: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {t}")
    print("=" * 64)


def have_stripe() -> bool:
    try:
        import stripe  # noqa: F401
        return True
    except ImportError:
        print("Falta `pip install stripe`. Corre:")
        print("    pip3 install stripe")
        return False


def run_scenario(label: str, pan: str, description: str) -> None:
    import stripe
    print(f"\n--- escenario: {label}  ({description}) ---")
    print(f"    PAN: {pan}")
    try:
        # 1) PaymentMethod con datos de tarjeta de prueba.
        pm = stripe.PaymentMethod.create(
            type="card",
            card={"number": pan, "exp_month": 12, "exp_year": 2030, "cvc": "123"},
        )
        print(f"    pm  : {pm.id}  brand={pm.card.brand} last4={pm.card.last4}")
    except stripe.error.CardError as e:
        print(f"    CardError al crear PaymentMethod: {e.user_message}")
        return
    except stripe.error.AuthenticationError as e:
        print(f"    Auth fallida: {e.user_message or e}")
        return
    except stripe.error.APIConnectionError as e:
        print(f"    No alcanza api.stripe.com (revisa internet/SSL): {e}")
        return
    except Exception as e:
        print(f"    Error inesperado ({type(e).__name__}): {str(e)[:120]}")
        return

    # 2) Customer.
    customer = stripe.Customer.create(
        name="Cliente Lab",
        description="creado desde payment-card-lab demo",
    )
    print(f"    cust: {customer.id}")

    # 3) Attach PM al Customer.
    stripe.PaymentMethod.attach(pm.id, customer=customer.id)

    # 4) PaymentIntent (cobro de USD $25.00 = 2500 cents).
    try:
        pi = stripe.PaymentIntent.create(
            amount=2500,
            currency="usd",
            customer=customer.id,
            payment_method=pm.id,
            confirm=True,
            description=f"Lab test charge ({label})",
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )
        print(f"    pi  : {pi.id}  status={pi.status}")
        if pi.status == "requires_action":
            # 3DS challenge requerido.
            na = pi.next_action or {}
            print(f"    !! Stripe pide autenticacion 3DS")
            print(f"       next_action.type = {na.get('type')}")
            print(f"       (en una app web, aqui se abre el modal de Stripe.js")
            print(f"        para que el cardholder complete el challenge)")
        elif pi.status == "succeeded":
            ch = stripe.Charge.retrieve(pi.latest_charge)
            print(f"    cobro: charge={ch.id} status={ch.status} amount={ch.amount/100} {ch.currency}")
            print(f"           outcome={ch.outcome.network_status} reason={ch.outcome.reason}")
    except stripe.error.CardError as e:
        # Decline correcto, esperado para los PAN tipo 4000000000000002.
        print(f"    DECLINED  code={e.code}  decline_code={getattr(e, 'decline_code', None)}")
        print(f"    mensaje: {e.user_message}")


def explain_test_mode() -> None:
    section("Que hace Stripe diferente para que estos PAN 'funcionen'")
    print("""
  * stripe.com tiene DOS bases:
      - LIVE: la real. Llaves sk_live_ y pk_live_. Cobros reales.
      - TEST: una replica de la API que acepta PANs publicados.
              Llaves sk_test_ y pk_test_. No mueve dinero.

  * Cuando mandas 4242 4242 4242 4242 con sk_test_:
      - Stripe lo reconoce porque ESTA EN SU BASE de pruebas.
      - Lo procesa como si fuera real: emite payment_method,
        crea payment_intent, decide aprobado/declinado segun el PAN.
      - El charge tiene status='succeeded' o un decline real.

  * Cuando mandas el mismo 4242 con sk_live_:
      - Stripe te devuelve "your card was declined" - porque la base
        de produccion no conoce ese PAN. Solo conoce PANs reales.

  * Cuando mandas un PAN inventado (uno generado por nuestro lab):
      - Test: 'invalid_number' (no esta en test DB)
      - Live: 'card_declined' (no esta en live DB tampoco)

  Esto explica la pregunta clave: para 'crear tu propio PAN', necesitas
  estar del lado de quien controla la base. En este lab tu controlas
  BancoLab; en Stripe Issuing tu puedes hacer que Stripe emita tarjetas
  reales con tu BIN; en un banco solo el banco puede.
""")


def run() -> None:
    if not have_stripe():
        return
    import stripe
    key = os.environ.get("STRIPE_TEST_KEY")
    if not key:
        section("STRIPE_TEST_KEY no esta exportada")
        print("""
  Para correr este demo:
    1. Crea cuenta gratis en https://dashboard.stripe.com/register
    2. Developers -> API keys -> 'Reveal test key' (sk_test_...)
    3. export STRIPE_TEST_KEY=sk_test_...
    4. python3 cli.py stripe-real
""")
        explain_test_mode()
        return
    if not key.startswith("sk_test_"):
        print(f"STRIPE_TEST_KEY debe empezar con sk_test_ (es: {key[:8]}...).")
        print("Negativa absoluta a correr contra sk_live_ desde este lab.")
        sys.exit(2)
    stripe.api_key = key
    stripe.api_version = "2024-06-20"

    section("Cliente Stripe real (sandbox / test mode)")
    print(f"  Llave: {key[:12]}...{key[-4:]}")
    print(f"  Endpoint: https://api.stripe.com")
    print(f"  Modo: TEST (sin movimiento de dinero real)")

    for label, pan, descr in SCENARIOS:
        run_scenario(label, pan, descr)

    explain_test_mode()


if __name__ == "__main__":
    run()
