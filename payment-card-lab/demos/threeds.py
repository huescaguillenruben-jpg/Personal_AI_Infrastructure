"""Demo 04: e-commerce con 3-D Secure.

Para un monto alto en CNP, el emisor exige 3DS:
  1. Primer intento sin CAVV -> soft decline 1A.
  2. El comercio inicia challenge, el ACS emite OTP.
  3. El usuario captura el OTP, el ACS valida y emite CAVV.
  4. Comercio reintenta con CAVV -> aprobada.
"""

from __future__ import annotations

import json

from ._setup import banner, build_world, fmt_money


def run() -> None:
    banner("Demo 04: e-commerce con 3-D Secure")
    w = build_world()
    # CVV correcto requerido en e-commerce.
    amount = 2_500_00

    # 1) Intento sin 3DS -> emisor pide challenge.
    rsp = w.terminal.ecommerce(w.card.pan, w.card.expiry_mmYY,
                               w.card.cvv, amount)
    rc = rsp.get("RESPONSE_CODE")
    print(f"E-commerce $2,500 sin 3DS -> RC={rc}  (1A = SCA requerida)")
    ecom = json.loads(rsp.get("ECOM_DATA"))
    cid, otp_demo = ecom["challenge_id"], ecom["otp_demo"]
    print(f"  Challenge id={cid}  OTP simulada={otp_demo}")

    # 2) Usuario "escribe" la OTP, ACS valida y emite CAVV.
    result = w.issuer.acs.verify(cid, otp_demo)
    print(f"  ACS verify -> success={result.success} eci={result.eci}")
    assert result.success and result.cavv

    # 3) Reintento con CAVV.
    rsp = w.terminal.ecommerce(w.card.pan, w.card.expiry_mmYY,
                               w.card.cvv, amount,
                               cavv=result.cavv, cavv_cid=cid)
    print(f"E-commerce $2,500 con CAVV -> RC={rsp.get('RESPONSE_CODE')}  auth={rsp.get('AUTH_CODE')}")
    print(f"  saldo disponible: {fmt_money(w.account.available_minor())}")


if __name__ == "__main__":
    run()
