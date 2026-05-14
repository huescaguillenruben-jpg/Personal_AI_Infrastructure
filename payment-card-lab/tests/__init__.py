"""Setup global de tests: silenciar el logger del lab."""

import logging

logging.getLogger("pailab").addHandler(logging.NullHandler())
logging.getLogger("pailab").propagate = False
