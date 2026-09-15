"""Application settings, loaded from environment variables or a local .env file."""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "mvp-subscription-api"
    app_version: str = "1.0.0"

    # Secret guarding this API. Distinct from the budget service's own key.
    api_key: str = "subscription-local-dev-key"

    database_url: str = "sqlite+aiosqlite:///./data/subscription.db"

    # --- Serviço de metas (componente secundária) ---
    budget_api_url: str = "http://localhost:8001"
    budget_api_key: str = "budget-local-dev-key"
    budget_api_timeout_seconds: float = 3.0
    budget_api_retries: int = 1

    # --- API externa de câmbio ---
    frankfurter_url: str = "https://api.frankfurter.dev/v1"
    frankfurter_timeout_seconds: float = 5.0
    fx_cache_ttl_seconds: int = 900
    # Cotação de emergência, guardada muito além do TTL normal: se a API externa
    # cair, o serviço responde com a última taxa conhecida em vez de falhar.
    fx_fallback_ttl_seconds: int = 604800

    # Encargos sobre cobranças em moeda estrangeira (IOF + spread do emissor), em
    # pontos percentuais. Zero mantém o custo na cotação pura de referência.
    # Alíquota negativa é recusada aqui: o serviço falha ao subir, com mensagem
    # clara, em vez de devolver um custo menor que a conversão.
    fx_fee_pct: Decimal = Field(default=Decimal("0"), ge=0)

    redis_url: str | None = None
    cache_ttl_seconds: int = 900

    seed_on_startup: bool = False
    idle_days_threshold: int = 30
    base_currency: str = "BRL"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
