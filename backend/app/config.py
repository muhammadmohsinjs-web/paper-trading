from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_OPENAI = "openai"
SUPPORTED_AI_PROVIDERS = {AI_PROVIDER_ANTHROPIC, AI_PROVIDER_OPENAI}


def _read_dotenv() -> dict[str, str]:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _get_value(*names: str, default: str) -> str:
    dotenv_values = _read_dotenv()
    for name in names:
        if name in os.environ:
            return os.environ[name]
        if name in dotenv_values:
            return dotenv_values[name]
    return default


def _get_bool(name: str, default: bool) -> bool:
    value = _get_value(name, default="" if default is False else "true")
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_list(*names: str) -> list[str]:
    value = _get_value(*names, default="")
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Paper Trading Backend"
    environment: str = "development"
    api_prefix: str = "/api"
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'paper_trading.db'}"
    database_echo: bool = False
    default_quote_asset: str = "USDT"
    default_symbol: str = "BTCUSDT"
    allowed_origins: list[str] = field(default_factory=list)

    # Binance
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"
    binance_rest_url: str = "https://api.binance.com"

    # Trading
    default_balance_usdt: float = 1000.0
    trading_interval_seconds: int = 300
    spot_fee_rate: float = 0.001
    bnb_discount_fee_rate: float = 0.00075

    # AI
    ai_provider: str = AI_PROVIDER_ANTHROPIC
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-3-5-sonnet-20240620"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ai_concurrent_calls: int = 3
    ai_timeout_seconds: int = 45
    ai_min_cooldown_seconds: int = 60
    ai_flat_market_threshold_pct: float = 0.2
    ai_max_tokens: int = 700
    ai_temperature: float = 0.2
    ai_input_cost_per_1m_tokens_usd: float = 3.0
    ai_output_cost_per_1m_tokens_usd: float = 15.0
    openai_input_cost_per_1m_tokens_usd: float = 0.0
    openai_output_cost_per_1m_tokens_usd: float = 0.0

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    @classmethod
    def from_env(cls) -> "Settings":
        prefix = "PAPER_TRADING_"
        environment = _get_value(f"{prefix}ENVIRONMENT", default=cls.environment)
        allowed_origins = _get_list(f"{prefix}ALLOWED_ORIGINS", "CORS_ORIGINS")
        if not allowed_origins and environment == "development":
            allowed_origins = [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
        return cls(
            app_name=_get_value(f"{prefix}APP_NAME", default=cls.app_name),
            environment=environment,
            api_prefix=_get_value(f"{prefix}API_PREFIX", default=cls.api_prefix),
            database_url=_get_value(
                f"{prefix}DATABASE_URL",
                "DATABASE_URL",
                default=cls.database_url,
            ),
            database_echo=_get_bool(f"{prefix}DATABASE_ECHO", cls.database_echo),
            default_quote_asset=_get_value(
                f"{prefix}DEFAULT_QUOTE_ASSET",
                default=cls.default_quote_asset,
            ),
            default_symbol=_get_value(
                f"{prefix}DEFAULT_SYMBOL",
                "TRADING_SYMBOL",
                default=cls.default_symbol,
            ),
            allowed_origins=allowed_origins,
            binance_ws_url=_get_value("BINANCE_WS_URL", default=cls.binance_ws_url),
            binance_rest_url=_get_value("BINANCE_REST_URL", default=cls.binance_rest_url),
            default_balance_usdt=float(_get_value("DEFAULT_BALANCE_USDT", default=str(cls.default_balance_usdt))),
            trading_interval_seconds=int(_get_value("TRADING_INTERVAL_SECONDS", default=str(cls.trading_interval_seconds))),
            spot_fee_rate=float(_get_value("SPOT_FEE_RATE", default=str(cls.spot_fee_rate))),
            bnb_discount_fee_rate=float(_get_value("BNB_DISCOUNT_FEE_RATE", default=str(cls.bnb_discount_fee_rate))),
            ai_provider=normalize_ai_provider(_get_value("AI_PROVIDER", default=cls.ai_provider)),
            ai_api_key=_get_value("AI_API_KEY", default=cls.ai_api_key),
            ai_base_url=_get_value("AI_BASE_URL", default=cls.ai_base_url),
            ai_model=_get_value("AI_MODEL", default=cls.ai_model),
            anthropic_api_key=_get_value("ANTHROPIC_API_KEY", default=cls.anthropic_api_key),
            anthropic_base_url=_get_value("ANTHROPIC_BASE_URL", default=cls.anthropic_base_url),
            anthropic_model=_get_value("ANTHROPIC_MODEL", default=cls.anthropic_model),
            openai_api_key=_get_value("OPENAI_API_KEY", default=cls.openai_api_key),
            openai_base_url=_get_value("OPENAI_BASE_URL", default=cls.openai_base_url),
            openai_model=_get_value("OPENAI_MODEL", default=cls.openai_model),
            ai_concurrent_calls=int(_get_value("AI_CONCURRENT_CALLS", default=str(cls.ai_concurrent_calls))),
            ai_timeout_seconds=int(_get_value("AI_TIMEOUT_SECONDS", default=str(cls.ai_timeout_seconds))),
            ai_min_cooldown_seconds=int(_get_value("AI_MIN_COOLDOWN_SECONDS", default=str(cls.ai_min_cooldown_seconds))),
            ai_flat_market_threshold_pct=float(_get_value("AI_FLAT_MARKET_THRESHOLD_PCT", default=str(cls.ai_flat_market_threshold_pct))),
            ai_max_tokens=int(_get_value("AI_MAX_TOKENS", default=str(cls.ai_max_tokens))),
            ai_temperature=float(_get_value("AI_TEMPERATURE", default=str(cls.ai_temperature))),
            ai_input_cost_per_1m_tokens_usd=float(_get_value("AI_INPUT_COST_PER_1M_TOKENS_USD", default=str(cls.ai_input_cost_per_1m_tokens_usd))),
            ai_output_cost_per_1m_tokens_usd=float(_get_value("AI_OUTPUT_COST_PER_1M_TOKENS_USD", default=str(cls.ai_output_cost_per_1m_tokens_usd))),
            openai_input_cost_per_1m_tokens_usd=float(_get_value("OPENAI_INPUT_COST_PER_1M_TOKENS_USD", default=str(cls.openai_input_cost_per_1m_tokens_usd))),
            openai_output_cost_per_1m_tokens_usd=float(_get_value("OPENAI_OUTPUT_COST_PER_1M_TOKENS_USD", default=str(cls.openai_output_cost_per_1m_tokens_usd))),
            host=_get_value("HOST", default=cls.host),
            port=int(_get_value("PORT", default=str(cls.port))),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def normalize_ai_provider(
    value: str | None,
    fallback: str = AI_PROVIDER_ANTHROPIC,
) -> str:
    provider = (value or fallback or AI_PROVIDER_ANTHROPIC).strip().lower()
    return provider if provider in SUPPORTED_AI_PROVIDERS else fallback


def default_ai_model_for_provider(provider: str, settings: Settings) -> str:
    if settings.ai_model.strip():
        return settings.ai_model.strip()
    normalized = normalize_ai_provider(provider)
    if normalized == AI_PROVIDER_OPENAI:
        return settings.openai_model
    return settings.anthropic_model


def ai_api_key_for_provider(provider: str, settings: Settings) -> str:
    if settings.ai_api_key.strip():
        return settings.ai_api_key.strip()
    normalized = normalize_ai_provider(provider)
    if normalized == AI_PROVIDER_OPENAI:
        return settings.openai_api_key
    return settings.anthropic_api_key


def ai_base_url_for_provider(provider: str, settings: Settings) -> str:
    if settings.ai_base_url.strip():
        return settings.ai_base_url.strip()
    normalized = normalize_ai_provider(provider)
    if normalized == AI_PROVIDER_OPENAI:
        return settings.openai_base_url
    return settings.anthropic_base_url
