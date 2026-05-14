# Payment Card Lab

Simulador local y educativo de cómo funciona una tarjeta de crédito/débito,
desde la emisión hasta el "tap to pay" con un wallet del celular.

> No se conecta a Visa, Mastercard, ni a ningún banco. Todo vive en memoria
> dentro de `simulator.py`. Sirve para **entender** el flujo, no para usar
> en pagos reales — y los PAN que genera no funcionan en ninguna terminal.

## Cómo correrlo

```bash
python3 simulator.py
```

Verás 8 pasos: alta de cuenta, emisión, compra OK, compra rechazada,
fondos insuficientes, alta en wallet, pago NFC y un intento de fraude
bloqueado por el criptograma.

## Mapa mental: qué hace cada actor

```
+----------+   PAN/CVV   +---------+    +-----------+    +---------+
| Cliente  | ----------> | Comercio| -> | Adquirente| -> | Emisor  |
+----------+             +---------+    +-----------+    +---------+
                                                              |
                                                              v
                                                         +---------+
                                                         | Cuenta  |  <- aqui vive el saldo
                                                         +---------+
```

| Pieza | En el código | Qué hace |
|---|---|---|
| **Emisor** (banco que da la tarjeta) | `class Issuer` | Crea cuentas, emite tarjetas, autoriza o rechaza cargos. Es el único que sabe el saldo. |
| **Cuenta** | `class Account` | Donde realmente vive el dinero. La tarjeta solo es un identificador que apunta aquí. |
| **Tarjeta** | `class Card` | PAN + expiry + CVV + titular. **No guarda saldo.** |
| **Comercio / terminal** | `class Merchant` | Solo reenvía los datos hacia el adquirente / emisor. |
| **Wallet del celular** | `class MobileWallet` | Guarda un **DPAN** (token) y una llave que en un teléfono real vive en el Secure Element. |

## Conceptos clave (con dónde mirar)

### 1. Algoritmo de Luhn — `luhn_valid` / `generate_pan`
Es una **suma de verificación pública** (ISO/IEC 7812). Detecta si tipeaste mal
un dígito. **No** valida si la tarjeta existe ni si tiene fondos.
Cualquier número de 16 dígitos puede pasar Luhn — lo que no puede hacer es
existir en la base del banco.

### 2. La tarjeta no tiene saldo — `Issuer.authorize`
Cuando pagas, la terminal manda PAN+expiry+CVV+monto al emisor. El emisor
busca la cuenta vinculada a ese PAN y decide. Por eso no existe ningún
"código local" que haga que una tarjeta diga "tengo fondos": esa decisión
ocurre en los servidores del banco.

Códigos ISO 8583 que verás:
- `00` aprobada
- `05` rechazo genérico (lo usamos también para criptograma malo)
- `14` PAN inválido / desconocido
- `51` fondos insuficientes
- `54` vencimiento incorrecto
- `82` CVV incorrecto

### 3. Tokenización (lo que hace Apple/Google Pay) — `Issuer.provision_token`
Cuando agregas una tarjeta al wallet:
1. La app del banco verifica que tú eres el dueño (3-D Secure, OTP, biometría).
2. El emisor genera un **DPAN** (Device PAN) distinto al PAN real.
3. Te entrega una llave criptográfica que se guarda en el Secure Element del teléfono.

Resultado: el comercio nunca ve tu PAN real. Si pierdes el celular,
el banco apaga ese DPAN específico y tu tarjeta física sigue viva.

### 4. Criptograma de un solo uso — `MobileWallet.tap_to_pay`
Cada tap genera un HMAC sobre `DPAN | monto | nonce` con la llave del dispositivo.
El emisor lo recalcula con su copia de la llave y compara. Por eso:
- Grabar el tap no sirve: el `nonce` cambia.
- Copiar el DPAN no sirve: sin la llave del Secure Element no puedes firmar.
- Por eso `[8]` del demo se rechaza con código `05`.

## Lo que **falta** vs. la realidad (intencionalmente)

Este lab simplifica un montón de cosas que en producción son obligatorias:

- Red de marca (Visa/Mastercard) entre adquirente y emisor.
- HSM físico certificado PCI para guardar llaves y validar CVV.
- 3-D Secure (Verified by Visa, Mastercard Identity Check).
- EMV: el chip ejecuta su propio "criptograma de transacción" (ARQC) firmado por la tarjeta.
- Cumplimiento PCI-DSS, tokenización certificada por la marca (TSP), KYC/AML.
- Liquidación: la diferencia entre **autorización** y **clearing/settlement**.

## Siguientes pasos para seguir aprendiendo

1. Implementa **clearing** separado de autorización (hoy lo hacemos en un solo paso).
2. Agrega **reversos** y **chargebacks**.
3. Reemplaza el HMAC por un **ARQC EMV** simplificado (DES/AES con un PAN-key derivado).
4. Mete un mini servidor HTTP que exponga `POST /authorize` y úsalo desde otra terminal.
5. Si quieres tocar dinero real **en sandbox**: lee la documentación de
   Stripe / Mercado Pago / Conekta y prueba con sus PAN de prueba oficiales
   (ej. `4242 4242 4242 4242`). Esos sí están conectados a una red ficticia
   real y nunca cobran de verdad.
