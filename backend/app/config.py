from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_OPENAI = "openai"
SUPPORTED_AI_PROVIDERS = {AI_PROVIDER_ANTHROPIC, AI_PROVIDER_OPENAI}
DEFAULT_SCAN_UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
    "APTUSDT", "OPUSDT", "ARBUSDT", "SUIUSDT", "SEIUSDT",
    "INJUSDT", "TIAUSDT", "FETUSDT", "RNDRUSDT", "WIFUSDT",
    "JUPUSDT", "STXUSDT", "IMXUSDT", "RUNEUSDT", "ARUSDT",
    "PENDLEUSDT", "ONDOUSDT", "FILUSDT", "ENAUSDT", "WLDUSDT",
]


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


def _resolve_database_url(value: str) -> str:
    prefixes = ("sqlite:///", "sqlite+aiosqlite:///")

    for prefix in prefixes:
        if not value.startswith(prefix):
            continue

        raw_path = value[len(prefix):]
        if not raw_path or raw_path == ":memory:" or raw_path.startswith("/"):
            return value

        path, sep, query = raw_path.partition("?")
        resolved = (BASE_DIR / path).resolve()
        suffix = f"?{query}" if sep else ""
        return f"{prefix}{resolved}{suffix}"

    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = "Paper Trading Backend"
    environment: str = "development"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    log_use_colors: bool = True
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'paper_trading.db'}"
    database_echo: bool = False
    default_quote_asset: str = "USDT"
    default_symbol: str = "BTCUSDT"
    default_scan_universe: list[str] = field(default_factory=lambda: DEFAULT_SCAN_UNIVERSE.copy())
    allowed_origins: list[str] = field(default_factory=list)

    # Binance
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"
    binance_rest_url: str = "https://api.binance.com"

    # Trading
    shared_wallet_enabled: bool = True
    default_balance_usdt: float = 1000.0
    trading_interval_seconds: int = 3600
    default_candle_interval: str = "1h"
    multi_coin_top_pick_count: int = 8
    multi_coin_max_concurrent_positions: int = 4
    multi_coin_selection_hour_utc: int = 0
    multi_coin_liquidity_floor_usdt: float = 1_000_000.0
    symbol_ownership_cooldown_hours: float = 4.0
    global_max_active_symbols: int = 20
    coordinated_pick_enabled: bool = True

    # Dynamic universe selection
    dynamic_universe_enabled: bool = True
    dynamic_universe_size: int = 40
    dynamic_universe_min_size: int = 15
    dynamic_universe_refresh_hours: float = 1.0
    candidate_pool_refresh_hours: float = 6.0
    universe_min_24h_volume_usdt: float = 500_000.0
    universe_min_price: float = 0.00001
    universe_min_listing_age_days: int = 14
    universe_volume_surge_weight: float = 0.30
    universe_volatility_quality_weight: float = 0.25
    universe_trend_clarity_weight: float = 0.20
    universe_liquidity_depth_weight: float = 0.15
    universe_relative_strength_weight: float = 0.10
    stablecoin_base_denylist: list[str] = field(default_factory=lambda: [
        "USDC", "USDT", "BUSD", "FDUSD", "TUSD", "USDP", "DAI", "USD1",
        "USDE", "USDD", "PYUSD", "FRAX",
    ])

    # Trade quality thresholds
    trade_quality_min_atr_pct: float = 0.25
    trade_quality_min_range_pct_20: float = 1.00
    trade_quality_min_range_pct_24h: float = 0.80
    trade_quality_min_abs_change_pct_24h: float = 0.40
    trade_quality_min_close_std_pct_24h: float = 0.20
    trade_quality_min_market_quality_score: float = 0.55
    trade_quality_min_move_vs_cost_multiple: float = 2.0
    trade_quality_min_directional_score: float = 0.30
    trade_quality_min_movement_quality_score: float = 0.55
    trade_quality_min_composite_market_quality_score: float = 0.50
    trade_quality_min_edge_strength: float = 0.60
    trade_quality_min_reward_to_cost_ratio: float = 1.25
    trade_quality_min_gross_reward_cost_multiple: float = 2.0
    trade_quality_min_net_reward_pct: float = 0.35
    trade_quality_min_net_rr: float = 1.35
    trade_quality_min_stop_distance_pct: float = 0.40
    trade_quality_min_take_profit_distance_pct: float = 0.80

    spot_fee_rate: float = 0.001
    bnb_discount_fee_rate: float = 0.00075

    # Risk management
    default_stop_loss_pct: float = 3.0
    default_max_drawdown_pct: float = 15.0
    default_risk_per_trade_pct: float = 2.0
    default_max_position_size_pct: float = 30.0

    # AI
    ai_provider: str = AI_PROVIDER_ANTHROPIC
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-3-5-sonnet-20240620"
    openai_api_key: str = ""
    openai_admin_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini"
    ai_concurrent_calls: int = 3
    ai_timeout_seconds: int = 45
    ai_min_cooldown_seconds: int = 60
    ai_flat_market_threshold_pct: float = 0.2
    ai_max_tokens: int = 700
    ai_temperature: float = 0.2
    ai_input_cost_per_1m_tokens_usd: float = 3.0
    ai_output_cost_per_1m_tokens_usd: float = 15.0
    openai_input_cost_per_1m_tokens_usd: float = 0.75
    openai_output_cost_per_1m_tokens_usd: float = 4.50

    # Twilio WhatsApp notifications
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "+14155238886"  # Twilio sandbox default
    twilio_whatsapp_to: list[str] = field(default_factory=list)

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
            log_level=_get_value(f"{prefix}LOG_LEVEL", "LOG_LEVEL", default=cls.log_level),
            log_use_colors=_get_bool(f"{prefix}LOG_USE_COLORS", cls.log_use_colors),
            database_url=_resolve_database_url(
                _get_value(
                    f"{prefix}DATABASE_URL",
                    "DATABASE_URL",
                    default=cls.database_url,
                )
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
            default_scan_universe=_get_list(f"{prefix}SCAN_UNIVERSE", "SCAN_UNIVERSE") or DEFAULT_SCAN_UNIVERSE.copy(),
            allowed_origins=allowed_origins,
            binance_ws_url=_get_value("BINANCE_WS_URL", default=cls.binance_ws_url),
            binance_rest_url=_get_value("BINANCE_REST_URL", default=cls.binance_rest_url),
            shared_wallet_enabled=_get_value("SHARED_WALLET_ENABLED", default="true").lower() in ("true", "1", "yes"),
            default_balance_usdt=float(_get_value("DEFAULT_BALANCE_USDT", default=str(cls.default_balance_usdt))),
            trading_interval_seconds=int(_get_value("TRADING_INTERVAL_SECONDS", default=str(cls.trading_interval_seconds))),
            default_candle_interval=_get_value("DEFAULT_CANDLE_INTERVAL", default=cls.default_candle_interval),
            multi_coin_top_pick_count=int(_get_value("MULTI_COIN_TOP_PICK_COUNT", default=str(cls.multi_coin_top_pick_count))),
            multi_coin_max_concurrent_positions=int(_get_value("MULTI_COIN_MAX_CONCURRENT_POSITIONS", default=str(cls.multi_coin_max_concurrent_positions))),
            multi_coin_selection_hour_utc=int(_get_value("MULTI_COIN_SELECTION_HOUR_UTC", default=str(cls.multi_coin_selection_hour_utc))),
            multi_coin_liquidity_floor_usdt=float(_get_value("MULTI_COIN_LIQUIDITY_FLOOR_USDT", default=str(cls.multi_coin_liquidity_floor_usdt))),
            symbol_ownership_cooldown_hours=float(_get_value("SYMBOL_OWNERSHIP_COOLDOWN_HOURS", default=str(cls.symbol_ownership_cooldown_hours))),
            global_max_active_symbols=int(_get_value("GLOBAL_MAX_ACTIVE_SYMBOLS", default=str(cls.global_max_active_symbols))),
            coordinated_pick_enabled=_get_bool("COORDINATED_PICK_ENABLED", cls.coordinated_pick_enabled),
            dynamic_universe_enabled=_get_bool("DYNAMIC_UNIVERSE_ENABLED", cls.dynamic_universe_enabled),
            dynamic_universe_size=int(_get_value("DYNAMIC_UNIVERSE_SIZE", default=str(cls.dynamic_universe_size))),
            dynamic_universe_min_size=int(_get_value("DYNAMIC_UNIVERSE_MIN_SIZE", default=str(cls.dynamic_universe_min_size))),
            dynamic_universe_refresh_hours=float(_get_value("DYNAMIC_UNIVERSE_REFRESH_HOURS", default=str(cls.dynamic_universe_refresh_hours))),
            candidate_pool_refresh_hours=float(_get_value("CANDIDATE_POOL_REFRESH_HOURS", default=str(cls.candidate_pool_refresh_hours))),
            universe_min_24h_volume_usdt=float(_get_value("UNIVERSE_MIN_24H_VOLUME_USDT", default=str(cls.universe_min_24h_volume_usdt))),
            universe_min_price=float(_get_value("UNIVERSE_MIN_PRICE", default=str(cls.universe_min_price))),
            universe_min_listing_age_days=int(_get_value("UNIVERSE_MIN_LISTING_AGE_DAYS", default=str(cls.universe_min_listing_age_days))),
            stablecoin_base_denylist=_get_list("STABLECOIN_BASE_DENYLIST") or [
                "USDC", "USDT", "BUSD", "FDUSD", "TUSD", "USDP", "DAI", "USD1",
                "USDE", "USDD", "PYUSD", "FRAX",
            ],
            trade_quality_min_atr_pct=float(_get_value("TRADE_QUALITY_MIN_ATR_PCT", default=str(cls.trade_quality_min_atr_pct))),
            trade_quality_min_range_pct_20=float(_get_value("TRADE_QUALITY_MIN_RANGE_PCT_20", default=str(cls.trade_quality_min_range_pct_20))),
            trade_quality_min_range_pct_24h=float(_get_value("TRADE_QUALITY_MIN_RANGE_PCT_24H", default=str(cls.trade_quality_min_range_pct_24h))),
            trade_quality_min_abs_change_pct_24h=float(_get_value("TRADE_QUALITY_MIN_ABS_CHANGE_PCT_24H", default=str(cls.trade_quality_min_abs_change_pct_24h))),
            trade_quality_min_close_std_pct_24h=float(_get_value("TRADE_QUALITY_MIN_CLOSE_STD_PCT_24H", default=str(cls.trade_quality_min_close_std_pct_24h))),
            trade_quality_min_market_quality_score=float(_get_value("TRADE_QUALITY_MIN_MARKET_QUALITY_SCORE", default=str(cls.trade_quality_min_market_quality_score))),
            trade_quality_min_move_vs_cost_multiple=float(_get_value("TRADE_QUALITY_MIN_MOVE_VS_COST_MULTIPLE", default=str(cls.trade_quality_min_move_vs_cost_multiple))),
            trade_quality_min_directional_score=float(_get_value("TRADE_QUALITY_MIN_DIRECTIONAL_SCORE", default=str(cls.trade_quality_min_directional_score))),
            trade_quality_min_movement_quality_score=float(_get_value("TRADE_QUALITY_MIN_MOVEMENT_QUALITY_SCORE", default=str(cls.trade_quality_min_movement_quality_score))),
            trade_quality_min_composite_market_quality_score=float(_get_value("TRADE_QUALITY_MIN_COMPOSITE_MARKET_QUALITY_SCORE", default=str(cls.trade_quality_min_composite_market_quality_score))),
            trade_quality_min_edge_strength=float(_get_value("TRADE_QUALITY_MIN_EDGE_STRENGTH", default=str(cls.trade_quality_min_edge_strength))),
            trade_quality_min_reward_to_cost_ratio=float(_get_value("TRADE_QUALITY_MIN_REWARD_TO_COST_RATIO", default=str(cls.trade_quality_min_reward_to_cost_ratio))),
            trade_quality_min_gross_reward_cost_multiple=float(_get_value("TRADE_QUALITY_MIN_GROSS_REWARD_COST_MULTIPLE", default=str(cls.trade_quality_min_gross_reward_cost_multiple))),
            trade_quality_min_net_reward_pct=float(_get_value("TRADE_QUALITY_MIN_NET_REWARD_PCT", default=str(cls.trade_quality_min_net_reward_pct))),
            trade_quality_min_net_rr=float(_get_value("TRADE_QUALITY_MIN_NET_RR", default=str(cls.trade_quality_min_net_rr))),
            trade_quality_min_stop_distance_pct=float(_get_value("TRADE_QUALITY_MIN_STOP_DISTANCE_PCT", default=str(cls.trade_quality_min_stop_distance_pct))),
            trade_quality_min_take_profit_distance_pct=float(_get_value("TRADE_QUALITY_MIN_TAKE_PROFIT_DISTANCE_PCT", default=str(cls.trade_quality_min_take_profit_distance_pct))),
            spot_fee_rate=float(_get_value("SPOT_FEE_RATE", default=str(cls.spot_fee_rate))),
            bnb_discount_fee_rate=float(_get_value("BNB_DISCOUNT_FEE_RATE", default=str(cls.bnb_discount_fee_rate))),
            default_stop_loss_pct=float(_get_value("STOP_LOSS_PCT", default=str(cls.default_stop_loss_pct))),
            default_max_drawdown_pct=float(_get_value("MAX_DRAWDOWN_PCT", default=str(cls.default_max_drawdown_pct))),
            default_risk_per_trade_pct=float(_get_value("RISK_PER_TRADE_PCT", default=str(cls.default_risk_per_trade_pct))),
            default_max_position_size_pct=float(_get_value("MAX_POSITION_SIZE_PCT", default=str(cls.default_max_position_size_pct))),
            ai_provider=normalize_ai_provider(_get_value("AI_PROVIDER", default=cls.ai_provider)),
            ai_api_key=_get_value("AI_API_KEY", default=cls.ai_api_key),
            ai_base_url=_get_value("AI_BASE_URL", default=cls.ai_base_url),
            ai_model=_get_value("AI_MODEL", default=cls.ai_model),
            anthropic_api_key=_get_value("ANTHROPIC_API_KEY", default=cls.anthropic_api_key),
            anthropic_base_url=_get_value("ANTHROPIC_BASE_URL", default=cls.anthropic_base_url),
            anthropic_model=_get_value("ANTHROPIC_MODEL", default=cls.anthropic_model),
            openai_api_key=_get_value("OPENAI_API_KEY", default=cls.openai_api_key),
            openai_admin_key=_get_value("OPENAI_ADMIN_KEY", "OPENAI_ADMIN_API_KEY", default=cls.openai_admin_key),
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
            twilio_account_sid=_get_value("TWILIO_ACCOUNT_SID", default=cls.twilio_account_sid),
            twilio_auth_token=_get_value("TWILIO_AUTH_TOKEN", default=cls.twilio_auth_token),
            twilio_whatsapp_from=_get_value("TWILIO_WHATSAPP_FROM", default=cls.twilio_whatsapp_from),
            twilio_whatsapp_to=_get_list("TWILIO_WHATSAPP_TO"),
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
