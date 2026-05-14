# Cómo correr el lab desde tu celular (sin instalar nada)

Si no tienes compu o no quieres instalar Python, usa **GitHub Codespaces**.
Es una compu Linux completa que vive en tu navegador, gratis (60 horas/mes
en cuentas personales).

## Pasos exactos (todo desde el browser del celular)

### 1. Abre GitHub en tu celular

Ve a **github.com** en el navegador (Safari/Chrome). Inicia sesión con
tu cuenta `huescaguillenruben-jpg` (la misma que usamos para el repo).

### 2. Entra al repo y a la rama

Navega a:
```
https://github.com/huescaguillenruben-jpg/Personal_AI_Infrastructure
```

Arriba a la izquierda hay un botón que dice **"main"** (selector de rama).
Tócalo y elige **`claude/payment-card-wallet-YZElm`**.

### 3. Crea un Codespace

En la misma página, busca el botón verde grande **"Code"** (o "Código").
Tócalo. Sale un menú con dos pestañas:
- **Local** (descarga)
- **Codespaces** (la que queremos)

Tócala. Da click en **"Create codespace on claude/payment-card-wallet-YZElm"**.

> Si es tu primer Codespace, GitHub te pide aceptar el plan gratuito. Acepta.

### 4. Espera ~45 segundos

Verás una pantalla negra con texto cargando. Está instalando Linux, Python
y las dependencias. Termina cuando aparezca VS Code en el navegador.

### 5. Abre la terminal y arranca el server

Abajo de VS Code hay una terminal. Si no la ves, tócale a las tres líneas
horizontales arriba a la izquierda → View → Terminal.

En la terminal escribe:

```bash
cd payment-card-lab
python3 api.py
```

Vas a ver el banner con TU PAN, CVV y vencimiento impresos en grande.

### 6. Abre la UI

Codespaces detecta automáticamente que el puerto 8765 se prendió y te
muestra un pop-up: **"Open in Browser"** o **"Make Public"**. Tócalo.

Se abre una pestaña nueva con la página del lab — tu tarjeta ya está
cargada, lista para usar.

### 7. Usa el lab

- Escribe un monto en el campo "Monto"
- Elige canal (swipe, chip, contactless, ecommerce)
- Toca "Cobrar"
- Mira cómo cambia el saldo y aparece la transacción en la tabla

Para el wallet:
- Toca "+ Agregar al wallet"
- Te genera un DPAN
- Escribe monto de tap y toca "Tap to Pay"

Para liquidar:
- Toca "Correr clearing batch"
- Las transacciones pasan de "authorized" a "captured"

### 8. Cuando termines

Vuelve a github.com → tu foto arriba a la derecha → **"Your codespaces"** →
los tres puntitos del codespace → **"Stop"** o **"Delete"**.

> Los Codespaces detenidos cuentan poco contra tu cuota; los eliminados,
> nada. No te van a cobrar.

---

## Alternativa: solo ver los números en la terminal (sin UI)

Si la UI no te interesa y solo quieres ver los flujos en texto:

```bash
cd payment-card-lab
python3 cli.py basic        # te imprime PAN/CVV y simula un cobro
python3 cli.py e2e          # demo end-to-end completo
python3 cli.py all          # los 7 demos seguidos
```

---

## Si Codespaces no te deja (cuota agotada, etc.)

Usa **Replit** como plan B:

1. Ve a **replit.com** desde tu celular, regístrate.
2. New Repl → Import from GitHub →
   `https://github.com/huescaguillenruben-jpg/Personal_AI_Infrastructure`
3. Branch: `claude/payment-card-wallet-YZElm`
4. En el shell de Replit: `cd payment-card-lab && python3 api.py`
5. Replit te muestra una "Webview" con la UI.

---

## Lo que NO funciona

- Abrir `http://127.0.0.1:8765/` en tu celular SIN nada corriendo →
  ese link apunta a tu propio teléfono, y ahí no hay servidor.
- Pedirme que yo te dé un link público → mi entorno no expone URLs
  públicas. La gracia es que tú prendas tu propio lab.
