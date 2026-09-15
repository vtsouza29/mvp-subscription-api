"""Encargos sobre cobranças em moeda estrangeira (IOF + spread do emissor)."""

import os
from decimal import Decimal

import pytest

from app.config import get_settings
from app.core.pricing import charge_multiplier, effective_fee_pct
from tests.conftest import subscription_payload


@pytest.fixture
def fee_of():
    """Aplica uma alíquota nas settings do processo e desfaz ao final."""
    original = os.environ.get("FX_FEE_PCT")

    def _apply(pct: str):
        os.environ["FX_FEE_PCT"] = pct
        get_settings.cache_clear()
        return get_settings()

    yield _apply

    if original is None:
        os.environ.pop("FX_FEE_PCT", None)
    else:
        os.environ["FX_FEE_PCT"] = original
    get_settings.cache_clear()


def test_moeda_estrangeira_recebe_o_encargo():
    assert charge_multiplier("USD", "BRL", Decimal("3.5")) == Decimal("1.035")


def test_moeda_base_e_isenta():
    """Cobrança em reais não é compra internacional: não há IOF nem spread."""
    assert charge_multiplier("BRL", "BRL", Decimal("3.5")) == Decimal("1")


def test_comparacao_de_moeda_ignora_caixa():
    assert charge_multiplier("brl", "BRL", Decimal("3.5")) == Decimal("1")


def test_aliquota_zero_mantem_a_conversao_pura():
    assert charge_multiplier("USD", "BRL", Decimal("0")) == Decimal("1")


def test_multiplicador_nao_passa_por_float():
    """0.1 + 0.2 em float não fecha em 0.3; em Decimal, fecha."""
    assert charge_multiplier("USD", "BRL", Decimal("0.1")) * Decimal("1000") == Decimal("1001.000")


def test_aliquota_negativa_e_recusada_na_configuracao(fee_of):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        fee_of("-1")


def test_encargo_exibido_vem_da_regra_e_nao_da_configuracao(fee_of):
    fee_of("3.5")
    assert effective_fee_pct("USD") == Decimal("3.5")
    assert effective_fee_pct("BRL") == Decimal("0")


async def test_assinatura_em_dolar_sai_com_encargo_na_resposta(client, fee_of):
    """Cotação de teste: 1 USD = R$ 5,00. Com 3,5%, R$ 50,00 viram R$ 51,75."""
    fee_of("3.5")
    payload = subscription_payload(amount=10.00, currency="USD", billing_cycle="MONTHLY")
    created = (await client.post("/api/v1/subscriptions", json=payload)).json()

    assert created["fx_rate_to_brl"] == 5.0, "o snapshot de câmbio continua puro"
    assert created["amount_brl"] == 51.75
    assert created["monthly_amount_brl"] == 51.75
    assert created["fx_fee_pct"] == 3.5


async def test_assinatura_em_reais_nao_recebe_encargo(client, fee_of):
    fee_of("3.5")
    payload = {
        "name": "Streaming Plus",
        "vendor": "Acme",
        "category": "STREAMING",
        "amount": 55.90,
        "currency": "BRL",
        "billing_cycle": "MONTHLY",
        "started_on": "2025-04-01",
        "next_renewal_on": "2026-10-01",
    }
    created = (await client.post("/api/v1/subscriptions", json=payload)).json()

    assert created["amount_brl"] == 55.90
    assert created["fx_fee_pct"] == 0
