# Referencia de tarjetas de prueba

Este documento concentra **todos los números que puedes usar** para probar
flujos de pago — y dónde "funciona" cada uno.

> ⚠️ Ninguno de estos números cobra dinero real ni se acepta en un comercio
> de producción. Intentarlos contra un sistema real no es solo inútil, es
> intento de fraude. Solo úsalos en los entornos indicados.

---

## 1. PANs generados por TU lab local (`payment-card-lab`)

Cada vez que corres el lab o `python3 api.py`, el emisor `BancoLab` genera
**un PAN nuevo al azar** con BIN `453219`. Ejemplos reales de corridas
(cambian cada vez):

| PAN | Vence | CVV | PSN |
|---|---|---|---|
| `4532198089874490` | 05/31 | 611 | 1 |
| `4532196733477322` | 05/31 | 467 | 1 |
| `4532191234567890` | 05/31 | 281 | 1 |

**Dónde funcionan**: dentro del proceso de Python mientras corre.
**Dónde no funcionan**: cualquier otro sistema (Stripe live, Stripe test,
Apple Pay, terminales reales).

Para generar un PAN nuevo:

```bash
python3 cli.py basic      # te imprime PAN/CVV/expiry al inicio
# o
python3 api.py
# y desde otra terminal:
curl -s -X POST http://127.0.0.1:8765/holders \
  -H 'Content-Type: application/json' -d '{"full_name":"Tu Nombre"}'
# ... continua con /accounts y /cards
```

---

## 2. PANs publicados oficialmente por Stripe (test mode)

Estos son **públicos**, vienen en https://docs.stripe.com/testing y solo
funcionan contra `api.stripe.com` con una llave `sk_test_...`.

### Visa

| PAN | Comportamiento |
|---|---|
| `4242 4242 4242 4242` | Aprobada |
| `4000 0566 5566 5556` | Aprobada (Visa Debit) |
| `4000 0027 6000 3184` | Aprobada con 3DS frictionless |
| `4000 0025 0000 3155` | **Requiere 3DS challenge** (authentication_required) |
| `4000 0082 6000 3178` | 3DS challenge, falla autenticación |

### Mastercard

| PAN | Comportamiento |
|---|---|
| `5555 5555 5555 4444` | Aprobada |
| `2223 0031 2200 3222` | Aprobada (rango 2-series) |
| `5200 8282 8282 8210` | Aprobada (debit) |

### American Express

| PAN | Comportamiento |
|---|---|
| `3782 822463 10005` | Aprobada |
| `3714 496353 98431` | Aprobada |

### Decline codes (para probar manejo de errores)

| PAN | Decline code |
|---|---|
| `4000 0000 0000 0002` | `card_declined` (genérico) |
| `4000 0000 0000 9995` | `insufficient_funds` |
| `4000 0000 0000 9987` | `lost_card` |
| `4000 0000 0000 9979` | `stolen_card` |
| `4000 0000 0000 0069` | `expired_card` |
| `4000 0000 0000 0127` | `incorrect_cvc` |
| `4000 0000 0000 0119` | `processing_error` |

### CVV y vencimiento (para todos los anteriores)

- **CVV**: cualquier número de 3 dígitos (4 para Amex). Por ejemplo `123`, `999`.
- **Vencimiento**: cualquier mes/año futuro. Por ejemplo `12/2030`, `01/2029`.
- **ZIP**: cualquier código de 5 dígitos. Por ejemplo `42424`.

### Cómo usarlos

```bash
# 1. Obtén tu llave de prueba (gratis, sin tarjeta de crédito)
#    https://dashboard.stripe.com/register -> Developers -> API keys
export STRIPE_TEST_KEY=sk_test_...

# 2. Demo comparativo (curl directo, sin SDK)
python3 cli.py stripe

# 3. Demo con SDK completo (PaymentIntent + 3DS)
python3 cli.py stripe-real

# 4. Emite TU propio PAN via Stripe Issuing
python3 cli.py stripe-issuing
```

---

## 3. PANs de prueba de otros gateways

### Mercado Pago (MX)

| PAN | Marca | Resultado |
|---|---|---|
| `5031 7557 3453 0604` | Master | APRO (aprobada) |
| `4509 9535 6623 3704` | Visa | APRO |
| `4013 5406 8274 6260` | Visa | OTHE (error) |
| `4389 3540 8049 4854` | Visa | CONT (pendiente) |

CVV: `123`. Vencimiento: `11/30`. Nombre del titular: `APRO` para aprobar
o `OTHE`/`CONT` para forzar otros estados.

Ver: https://www.mercadopago.com.mx/developers/es/docs/checkout-api/integration-test/test-cards

### Conekta (MX)

| PAN | Marca | Resultado |
|---|---|---|
| `4242 4242 4242 4242` | Visa | Aprobada |
| `4000 0000 0000 0002` | Visa | Declinada |
| `5555 5555 5555 4444` | Master | Aprobada |

Ver: https://developers.conekta.com/docs/tarjetas-de-prueba

### Openpay (MX)

| PAN | Marca | Resultado |
|---|---|---|
| `4111 1111 1111 1111` | Visa | Aprobada |
| `4000 0000 0000 0002` | Visa | Declinada |

---

## 4. Stripe Issuing — emite tu propio PAN real (test mode)

Si quieres que el PAN sea **tuyo** y no de Stripe, usa Stripe Issuing.
Funciona contra Stripe sandbox y te da:

- PAN nuevo emitido por Stripe a tu nombre
- CVV
- Vencimiento real
- Capacidad de simular cargos contra esa tarjeta

```bash
export STRIPE_TEST_KEY=sk_test_...
python3 cli.py stripe-issuing
```

Salida típica:

```
1. Crear Cardholder
   cardholder_id: ich_1Q...
   status:        active

2. Emitir tarjeta virtual
   card_id: ic_1Q...  brand: visa  last4: 4242

3. Recuperar PAN + CVV completos
   PAN:         4242 4242 4242 4242     <- TU PAN (cambia cada corrida)
   CVV:         847
   Vencimiento: 03/29
```

---

## 5. Qué hace que un PAN "funcione"

Resumen para que no se te olvide:

| PAN | Vive en | Responde a | Tipo |
|---|---|---|---|
| Lab local (`4532...`) | RAM de tu proceso | Tu `Issuer.authorize()` | Sintético, volátil |
| Stripe test (`4242...`) | Base test de Stripe | `api.stripe.com` con `sk_test_` | Sintético, persistente en Stripe |
| Stripe Issuing test | Tu cuenta Stripe (test) | `api.stripe.com` con `sk_test_` | Emitido a ti |
| Stripe Issuing live | Tu cuenta Stripe (prod) | Cualquier comercio | Real, mueve dinero |
| Real de tu banco | Base prod del banco | Cualquier comercio | Real, mueve dinero |

La única manera de "crear tu propio PAN funcional" sin ser un banco:
**Stripe Issuing** (o Pomelo / Marqeta / Galileo para LATAM).
