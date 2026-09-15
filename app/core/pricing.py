"""Encargos sobre cobranças em moeda estrangeira.

A cotação guardada em ``fx_rate_to_brl`` é a taxa de referência do Banco Central
Europeu, sem impostos: é o registro de quanto a assinatura custava quando foi
contratada. O que a fatura do cartão cobra, porém, é mais do que isso — há IOF
sobre a compra internacional e o spread do emissor.

Esse encargo é uma política do meio de pagamento, não uma característica do
contrato: quando a alíquota muda, ela passa a valer para todas as cobranças
seguintes de uma vez. Por isso ele vive na configuração (``FX_FEE_PCT``) e é
aplicado no cálculo, em vez de ser congelado junto do snapshot de câmbio.
"""

from decimal import Decimal

from app.config import get_settings


def charge_multiplier(currency: str, base_currency: str, fee_pct: Decimal) -> Decimal:
    """Fator que converte o valor já convertido em reais no valor efetivamente pago.

    Exemplo: com ``fee_pct`` de 3.5 e uma assinatura em dólar, o resultado é
    ``Decimal("1.035")`` — R$ 100,00 de conversão viram R$ 103,50 na fatura.

    Args:
        currency: moeda da assinatura (ex.: ``"USD"``).
        base_currency: moeda base da aplicação (ex.: ``"BRL"``).
        fee_pct: encargo total em pontos percentuais, vindo da configuração.

    Returns:
        O multiplicador a aplicar sobre o valor convertido.
    """
    # Cobrança já feita em reais não é compra internacional: não há IOF nem spread.
    if currency.upper() == base_currency.upper():
        return Decimal("1")

    # Tudo em Decimal: um float aqui traria de volta o erro de centavo que o
    # MoneyType existe para evitar. Alíquota negativa é recusada na configuração
    # (ver Settings.fx_fee_pct), e não silenciada aqui.
    return Decimal("1") + fee_pct / Decimal("100")


def with_fee(amount_brl: Decimal, currency: str) -> Decimal:
    """Aplica o encargo configurado sobre um valor já convertido em reais."""
    settings = get_settings()
    return amount_brl * charge_multiplier(currency, settings.base_currency, settings.fx_fee_pct)


def effective_fee_pct(currency: str) -> Decimal:
    """Encargo que de fato incidiu sobre esta moeda, em pontos percentuais.

    Derivado de ``charge_multiplier``, e não lido direto da configuração: assim a
    resposta da API nunca diverge do valor cobrado, qualquer que seja a regra.
    """
    settings = get_settings()
    multiplier = charge_multiplier(currency, settings.base_currency, settings.fx_fee_pct)
    return (multiplier - Decimal("1")) * Decimal("100")
