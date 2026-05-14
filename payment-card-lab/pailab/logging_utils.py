"""PAN/CVV masking para logs.

PCI-DSS requisito 3.3: en cualquier display/log, solo los primeros 6
y los ultimos 4 digitos del PAN pueden mostrarse en claro. El CVV
NUNCA se almacena ni se loguea.
"""

from __future__ import annotations

import logging
import re


_PAN_RE = re.compile(r"\b(\d{6})(\d{4,9})(\d{4})\b")
_CVV_RE = re.compile(r"\bcvv\s*[:=]\s*(\d{3,4})\b", re.IGNORECASE)
_TRACK2_RE = re.compile(r"(\d{6})\d+(\d{4})=\d+")


def mask_pan(pan: str) -> str:
    """Devuelve `123456******1234`."""
    if not pan or not pan.isdigit() or len(pan) < 12:
        return "*" * len(pan or "")
    return pan[:6] + "*" * (len(pan) - 10) + pan[-4:]


def scrub(text: str) -> str:
    """Reemplaza PANs, CVVs y track2 que aparezcan en `text`."""
    text = _PAN_RE.sub(lambda m: m.group(1) + "*" * len(m.group(2)) + m.group(3), text)
    text = _CVV_RE.sub("cvv=***", text)
    text = _TRACK2_RE.sub(r"\1******\2=****", text)
    return text


class PCIFilter(logging.Filter):
    """Filtro para el logger raiz que aplica scrub a cada record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        if record.args:
            record.args = tuple(scrub(a) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configura el logger raiz con PCIFilter. Idempotente."""
    root = logging.getLogger("pailab")
    if getattr(root, "_pci_configured", False):
        return root
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(name)s %(levelname)s %(message)s"))
    handler.addFilter(PCIFilter())
    root.addHandler(handler)
    root._pci_configured = True  # type: ignore[attr-defined]
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"pailab.{name}")
