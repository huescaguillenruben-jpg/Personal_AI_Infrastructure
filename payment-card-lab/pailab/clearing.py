"""Clearing y settlement entre adquirente, red y emisor.

En la realidad:
  1. El comercio cierra el dia ("batch close") y el adquirente envia
     un archivo de presentment a la red (clearing file).
  2. La red consolida y manda a cada emisor sus archivos.
  3. El emisor postea los cargos definitivos al cliente.
  4. Los fondos se mueven entre bancos via cuentas de liquidacion
     (settlement), tipicamente T+1 o T+2.

Aqui simulamos el batch:
  * Por cada PendingAuth del adquirente, llamamos al emisor para capturar.
  * El emisor mueve el hold a posted en el ledger del cliente.
  * El adquirente marca settled e incrementa el payable al comercio.
"""

from __future__ import annotations

from .logging_utils import get_logger


log = get_logger("clearing")


class ClearingEngine:
    """Orquesta el batch entre 1 adquirente y N emisores."""

    def __init__(self, acquirer, issuers_by_bin: dict, tsps: list | None = None):
        self.acquirer = acquirer
        self.issuers_by_bin = issuers_by_bin
        self.tsps = tsps or []

    def _resolve_issuer(self, pan_first6: str):
        # Match directo
        if pan_first6 in self.issuers_by_bin:
            return self.issuers_by_bin[pan_first6]
        # Si pertenece a un TSP, no podemos resolver con primeros 6 solo:
        # delegamos a los emisores conocidos preguntandoles si tienen ese DPAN.
        for issuer in self.issuers_by_bin.values():
            for tok_dpan in (t.dpan for t in
                             [t for pan in issuer.cards
                              for t in issuer.tsp.tokens_of(pan)]):
                if tok_dpan.startswith(pan_first6):
                    return issuer
        return None

    def run_batch(self) -> dict:
        """Captura cada pending y luego liquida."""
        captured_now = 0
        for p in list(self.acquirer.pending_auths):
            issuer = self._resolve_issuer(p.pan_first6)
            if issuer is None:
                log.warning("Sin emisor para bin %s", p.pan_first6)
                continue
            try:
                issuer.capture(p.txn_id)
                self.acquirer.mark_captured(p.txn_id)
                captured_now += 1
            except Exception as e:
                log.warning("Capture fallo txn=%s err=%s", p.txn_id, e)
        settled = self.acquirer.settle_batch()
        return {"captured_now": captured_now, "settled": settled}
