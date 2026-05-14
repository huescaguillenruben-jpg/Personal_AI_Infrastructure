# Payment Card Lab

Laboratorio local de un sistema de pagos con tarjeta, simulando todos
los actores reales que intervienen entre un PAN y un wallet del celular:

```
  Tarjetahabiente              Comercio              Sistema bancario
  ----------------             ---------             -----------------
  +-----------+      +-----------+    +-----------+    +-----------+
  | Card / SE | ---> | Terminal  | -> | Acquirer  | -> |  Network  |
  +-----------+      +-----------+    +-----------+    +-----+-----+
        ^                                                    |
        |                                                    v
        |                                              +-----+-----+
        |                                              |  Issuer   |
        |  provisionado                                |   (HSM,   |
        +-------- TSP <---- DPAN ---------------------+|   ledger, |
                                                      |   fraude, |
                                                      |   ACS 3DS)|
                                                      +-----------+
```

**Esto NO se conecta a Visa, Mastercard ni a ningún banco real.** Los
PAN que genera son sintéticos y no funcionan en ninguna terminal de
verdad. El propósito es entender, en código que puedes leer y modificar,
qué hace cada pieza.

## TL;DR

```bash
# Demos individuales:
python3 cli.py basic       # swipe (banda)
python3 cli.py emv         # chip EMV + ARQC + anti-replay con ATC
python3 cli.py wallet      # tokenización + tap NFC + suspensión de DPAN
python3 cli.py threeds     # 3-D Secure (CAVV + ECI)
python3 cli.py fraud       # velocidad, geo, MCC riesgosos
python3 cli.py clearing    # batch de captura + settlement
python3 cli.py e2e         # todo junto + reverso + reporte

# Todos:
python3 cli.py all

# Tests:
python3 -m unittest discover -t .

# API HTTP (stdlib, solo localhost):
python3 api.py    # luego curl http://127.0.0.1:8765/health
```

## Estructura

```
payment-card-lab/
├── pailab/                          # paquete principal
│   ├── luhn.py                      # checksum Luhn + generación de PANs sintéticos
│   ├── crypto.py                    # HSM, CVV, EMV ARQC, criptogramas de token
│   ├── errors.py                    # códigos de respuesta ISO 8583
│   ├── logging_utils.py             # masking PCI-DSS de PAN/CVV en logs
│   ├── iso8583.py                   # MTI y DEs como dict serializable
│   ├── lifecycle.py                 # máquina de estados de tarjeta
│   ├── models.py                    # dataclasses: Account, Card, Token, Txn
│   ├── ledger.py                    # libro mayor con holds / posted / refund
│   ├── fraud.py                     # reglas: velocidad, MCC, geo, monto
│   ├── tds.py                       # ACS 3-D Secure (OTP, CAVV)
│   ├── tsp.py                       # Token Service Provider (DPAN <-> PAN)
│   ├── issuer.py                    # emisor: HSM + ledger + fraude + ACS
│   ├── acquirer.py                  # adquirente: terminales + payables
│   ├── network.py                   # red de marca: ruteo por BIN o TSP
│   ├── terminal.py                  # POS y gateway e-commerce
│   ├── wallet.py                    # wallet móvil + Secure Element simulado
│   └── clearing.py                  # batch de captura + settlement
├── demos/                           # demos numerados
├── tests/                           # 45 unit tests, stdlib unittest
├── api.py                           # HTTP API local (stdlib http.server)
├── cli.py                           # corre cualquier demo
├── simulator.py                     # entry point = e2e
└── README.md
```

## Las tres ideas centrales (de nuevo, ahora con el código)

### 1. El saldo no vive en la tarjeta

Mira `pailab/ledger.py`. Cada `Account` tiene `posted_minor` y `held_minor`.
La tarjeta solo apunta a una cuenta. Cuando el comercio pide autorización:

```
Issuer.authorize(req)
    -> validaciones (Luhn, CVV, vencimiento, lifecycle)
    -> FraudEngine.evaluate(req)
    -> Ledger.hold(account_id, amount)        # si no alcanza: RC=51
    -> Transaction registrada
```

**Conclusión**: no hay un "código en la tarjeta" que le diga al mundo
que tiene fondos. El emisor (Issuer) es la única autoridad y consulta
su `Ledger`.

### 2. El wallet emite un DPAN distinto

`MobileWallet.add_card()` llama al issuer, que delega al `TSP`. El TSP
genera un DPAN con su propio BIN (`999900` en este lab) y una llave
HMAC. La llave se guarda en `_SecureElement` (clase con underscore: no
expone bytes hacia afuera; solo el método `sign()` puede usarla).

```python
phone.add_card(issuer=iss, pan=card.pan, expiry=..., cvv=...)
# -> internamente:
#    issuer.provision_token(...)
#    -> verifica PAN/CVV con HSM
#    -> tsp.provision(...) genera DPAN y key
#    -> _SecureElement.store(dpan, key, ...)
```

Cuando suspendes el DPAN (`issuer.tsp.suspend(dpan)`), el plástico
físico sigue funcionando. Eso es exactamente lo que pasa cuando pierdes
el celular y reportas el wallet.

### 3. Cada tap es único — y por qué

`Wallet.tap_to_pay()` genera un `nonce` aleatorio, le pide al SE que
firme `dpan | amount | nonce` con la llave, y manda el HMAC al terminal.
El emisor reconstruye el mismo HMAC con su copia de la llave y compara
en tiempo constante.

```python
# wallet.py
nonce = secrets.token_hex(8)
cryptogram = self._se.sign(self._hsm, dpan, amount_minor, nonce)
```

Por qué los ataques no funcionan:

| Ataque | Por qué falla |
|---|---|
| Replay: grabar un tap y reusarlo | El emisor desafía un `nonce` distinto cada vez |
| Clonar el DPAN | El cryptogram requiere la llave del SE, que nunca sale del SE |
| Forjar el cryptogram | Es un HMAC; sin la llave es indistinguible de aleatorio |

En el demo 07 (e2e) verás el paso `[5] NFC con crypto falso -> RC=85`:
mandar el mismo DPAN con un HMAC inventado falla con `85` (Crypto failure).

## EMV ARQC: el "código del chip"

`crypto.py` implementa la jerarquía de llaves EMV:

```
IMK_AC (del emisor, en el HSM)
  └── MK_AC_card = derive(IMK_AC, PAN || PSN)              # una por tarjeta
        └── SK_AC = derive(MK_AC_card, ATC || UN)          # una por transacción
              └── ARQC = MAC(SK_AC, datos de la transacción)
```

Datos firmados por el ARQC: monto, moneda, país, MCC, ATC, UN.
Cambiar **cualquiera** invalida el ARQC. El ATC es un contador que
solo crece — si el emisor ve un ATC <= al último visto, declina con
`85` (anti-replay).

> Nota técnica: el EMV real usa 3DES; aquí usamos HMAC-SHA256 truncado
> porque stdlib de Python no incluye 3DES. La estructura de derivación
> y las propiedades de seguridad son las mismas; solo cambia el primitivo.

## 3-D Secure

`tds.py` implementa un ACS minimal. Para CNP con monto alto, el emisor
emite un challenge_id + OTP. El usuario captura la OTP, el ACS valida,
emite un `CAVV` (firma) y un `ECI = "05"`. El comercio reintenta con
`cavv` y `cavv_cid` en `ECOM_DATA` (DE 112).

`acs.verify_cavv(...)` recalcula el CAVV con `pan | amount | challenge_id`,
así que el CAVV está atado a ese monto exacto — no se puede reusar para
otra transacción.

## Fraude

`fraud.py` aplica reglas con scoring acumulativo:

| Regla | Puntos | Trigger |
|---|---|---|
| Velocidad | +40 | >= 5 txn en 60s |
| Límite diario | +50 | suma diaria > 50,000 MXN |
| MCC riesgoso | +20 | 6051/7995/5967/4829 |
| Geo mismatch | +25 | país terminal != país home |
| CNP monto alto sin 3DS | n/a | exige 3DS si amount >= 1,500 MXN |

`score >= 80 -> decline | score >= 40 + CNP -> 3DS | score >= 40 + CP -> decline`

El mapeo a RC ISO 8583 lo hace `_rc_for_fraud()` en `issuer.py`:
`61` para límite, `65` para velocidad, `62` para PAN bloqueado, `05` default.

## Clearing

Una vez autorizada, la txn está "en hold". El comercio cierra batch al
final del día y el `ClearingEngine` corre:

```
para cada PendingAuth en acquirer:
   issuer.capture(txn_id)          # mueve hold -> posted en ledger
   acquirer.mark_captured(txn_id)
acquirer.settle_batch()             # incrementa payable del comercio
```

En la vida real esto se mueve por archivos clearing entre red y emisor
y la liquidación T+1/T+2 va por cuentas de settlement del banco central.

## Endpoints HTTP

```
GET  /health
POST /holders                   {full_name, country?}
POST /accounts                  {holder_id, type, initial_deposit_minor, currency?}
POST /cards                     {account_id}
POST /authorize                 {pan, expiry, cvv?, amount_minor, pos_entry, ...}
POST /capture                   {txn_id}
POST /reverse                   {txn_id}
POST /wallet/provision          {pan, expiry, cvv, device_id, provider?}
POST /wallet/tap                {dpan, amount_minor, cryptogram, nonce, ...}
GET  /accounts/{account_id}
```

## Lo que **no** está vs. la realidad

| Falta | Por qué |
|---|---|
| Binario ISO 8583 (bitmap + BCD) | usamos JSON; misma estructura lógica |
| 3DES en EMV | usamos HMAC-SHA256; misma jerarquía de llaves |
| HSM físico FIPS 140-3 | el "HSM" es una clase de Python |
| Red entre adquirente y emisor por TCP | los actores se llaman directo |
| Liquidación interbancaria por SPEI/SWIFT | el `Acquirer` solo trackea payable |
| Persistencia | todo es en memoria; reinicia y se va |
| TLS, mTLS, certificados de red, PKI | n/a |
| KYC/AML, sanciones (OFAC), PEPs | `kyc_verified=True` por default |
| Disputas y chargebacks | hay `refund()` pero no flujo de dispute |
| Carga / batch real, archivos VSS-110, etc. | no |

## Roadmap si quieres seguir

1. Sustituir HMAC por una implementación de 3DES en puro Python para que
   el ARQC sea byte-exacto a EMV Book 2.
2. Implementar un encoder/decoder binario de ISO 8583 con bitmap.
3. Agregar disputes (chargeback codes 4853, 4837, etc.) y un flujo de
   representación al emisor.
4. Conectar el `ClearingEngine` a archivos CSV/JSON en disco para
   simular el ciclo T+1.
5. Reemplazar el HTTP server stdlib por uno asíncrono y agregar mTLS.
