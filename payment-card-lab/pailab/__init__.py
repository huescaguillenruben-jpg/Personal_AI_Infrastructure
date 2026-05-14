"""
pailab — laboratorio educativo de un sistema de pagos con tarjeta.

NO se conecta a redes reales. Todo ocurre en memoria.

Modulos:
    luhn         Algoritmo de Luhn y generacion de PANs sinteticos.
    errors       Codigos de respuesta ISO 8583 como enum.
    logging_utils Masking de PAN/CVV para logs (PCI-DSS req. 3.3).
    models       Dataclasses: Account, Card, Holder, Token, Transaction.
    lifecycle    Maquina de estados del ciclo de vida de una tarjeta.
    crypto       HSM simulado, derivacion de llaves EMV, ARQC.
    iso8583      Codificador/decodificador minimo (JSON, no binario).
    ledger       Libro mayor (debits/credits, holds, posted).
    fraud        Reglas: velocidad, MCC, geografia, monto.
    tds          3-D Secure simulado.
    tsp          Token Service Provider (DPAN <-> PAN).
    issuer       Banco emisor.
    acquirer     Banco adquirente.
    network      Red de marca (Visa/Mastercard role).
    terminal     Terminal POS.
    wallet       Wallet movil con Secure Element simulado.
    clearing     Liquidacion en lote.
"""

__version__ = "1.0.0"
