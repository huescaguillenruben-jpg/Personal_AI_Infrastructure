.PHONY: help install test demo basic emv wallet threeds fraud clearing e2e all api web stripe issuing clean lint

help:
	@echo "Payment Card Lab — comandos"
	@echo ""
	@echo "  make install     Instala dependencias (solo stripe SDK, opcional)"
	@echo "  make test        Corre 45 unit tests"
	@echo "  make api         Levanta API + UI en http://127.0.0.1:8765"
	@echo "  make e2e         Demo end-to-end completo"
	@echo "  make all         Corre los 7 demos locales"
	@echo "  make basic       Demo swipe"
	@echo "  make emv         Demo EMV chip + ARQC"
	@echo "  make wallet      Demo tokenizacion + NFC"
	@echo "  make threeds     Demo 3-D Secure"
	@echo "  make fraud       Demo reglas antifraude"
	@echo "  make clearing    Demo batch clearing"
	@echo "  make stripe      Demo comparativo (necesita STRIPE_TEST_KEY)"
	@echo "  make issuing     Demo Stripe Issuing (necesita STRIPE_TEST_KEY)"
	@echo "  make clean       Limpia __pycache__"

install:
	pip install -r requirements.txt

test:
	python3 -m unittest discover -t .

api:
	python3 api.py

e2e:
	python3 cli.py e2e

basic:    ; python3 cli.py basic
emv:      ; python3 cli.py emv
wallet:   ; python3 cli.py wallet
threeds:  ; python3 cli.py threeds
fraud:    ; python3 cli.py fraud
clearing: ; python3 cli.py clearing
all:      ; python3 cli.py all
stripe:   ; python3 cli.py stripe
issuing:  ; python3 cli.py stripe-issuing

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

lint:
	python3 -m py_compile $$(find pailab demos tests -name '*.py')
	@echo "syntax OK"
