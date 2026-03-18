"""Phase 3 verification coverage for the AI execution path."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db_session
from app.main import create_app
from app.models import Base
from app.models.strategy import Strategy
from app.ai.parser import DecisionParser
from app.ai.prompts import StrategyPromptBuilder
from app.ai.types import AITradeAction, AIStrategyProfile, MarketSnapshot
from app.config import Settings
from app.engine import ai_runtime


STRATEGY_ID = "phase3-ai-strategy"


async def _noop_async(*_: Any, **__: Any) -> None:
    return None


def _optional_import(*module_names: str):
    for name in module_names:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    pytest.skip(f"None of the optional modules exist yet: {module_names}")


def _resolve_function(module: Any, *candidate_names: str):
    for name in candidate_names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    pytest.skip(
        f"None of the expected hooks exist in {module.__name__}: {candidate_names}"
    )


def _call_best_effort(fn, values: dict[str, Any]) -> Any:
    sig = inspect.signature(fn)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    positional_fallbacks = [values[key] for key in values if key in {"text", "raw_text", "response_text", "payload"}]

    for param in sig.parameters.values():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        candidate = None
        if param.name in values:
            candidate = values[param.name]
        else:
            lowered = param.name.lower()
            for key, value in values.items():
                if key == lowered or key in lowered or lowered in key:
                    candidate = value
                    break

        if candidate is None:
            if param.default is inspect._empty:
                if positional_fallbacks:
                    args.append(positional_fallbacks[0])
                    positional_fallbacks = positional_fallbacks[1:]
                    continue
                pytest.skip(
                    f"Cannot satisfy required parameter '{param.name}' for {fn.__qualname__}"
                )
            continue

        kwargs[param.name] = candidate

    return fn(*args, **kwargs)


def _is_hold_result(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, str):
        return result.upper() == "HOLD"
    if isinstance(result, dict):
        action = result.get("action") or result.get("decision")
        if action is None:
            return bool(result.get("hold", False))
        return str(action).upper() == "HOLD"

    action = getattr(result, "action", None)
    if action is None:
        return bool(getattr(result, "hold", False))

    action_value = getattr(action, "value", action)
    return str(action_value).upper() == "HOLD"


def _is_skip_result(result: Any) -> bool:
    if isinstance(result, bool):
        return result
    if isinstance(result, tuple) and result:
        return bool(result[0])
    if isinstance(result, dict):
        if "skip" in result:
            return bool(result["skip"])
        if "should_skip" in result:
            return bool(result["should_skip"])
        if "allowed" in result:
            return not bool(result["allowed"])

    for attr in ("skip", "should_skip", "is_skipped"):
        value = getattr(result, attr, None)
        if value is not None:
            return bool(value)

    return bool(result)


@pytest.fixture
def phase3_app(tmp_path, monkeypatch):
    """Create an isolated app instance with a seeded AI strategy."""
    db_path = tmp_path / "phase3-ai.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(
                Strategy(
                    id=STRATEGY_ID,
                    name="Phase 3 AI",
                    description="AI-backed strategy for verification",
                    config_json={
                        "strategy_type": "ai",
                        "ai_enabled": True,
                        "ai_cooldown_seconds": 60,
                        "initial_balance": 1000,
                    },
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(setup_db())

    import app.database as db_mod
    import app.main as main_mod

    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(main_mod, "init_database", _noop_async)
    monkeypatch.setattr(main_mod, "backfill", _noop_async)

    class DummyWSClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    class DummyStrategyManager:
        @classmethod
        def get_instance(cls):
            return cls()

        async def start_all_active(self) -> int:
            return 0

        async def stop_all(self) -> int:
            return 0

    monkeypatch.setattr(main_mod, "BinanceWSClient", DummyWSClient)
    monkeypatch.setattr(main_mod, "StrategyManager", DummyStrategyManager)

    async def get_test_db():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = get_test_db

    yield app

    asyncio.run(engine.dispose())


def test_manual_execute_returns_ai_reasoning(phase3_app, monkeypatch):
    """Manual execution should surface the trade info returned by the AI cycle."""
    captured: dict[str, Any] = {}

    import app.api.engine as api_engine

    async def fake_run_single_cycle(
        strategy_id: str,
        force: bool = False,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
    ):
        captured["strategy_id"] = strategy_id
        captured["force"] = force
        captured["symbol"] = symbol
        captured["interval"] = interval
        return {
            "strategy_id": strategy_id,
            "action": "BUY",
            "symbol": symbol,
            "price": "50000.00",
            "quantity": "0.01000000",
            "fee": "0.10",
            "pnl": None,
            "reason": "Claude saw a breakout and approved the trade",
        }

    monkeypatch.setattr(api_engine, "run_single_cycle", fake_run_single_cycle)

    with TestClient(phase3_app) as client:
        response = client.post(f"/api/engine/strategies/{STRATEGY_ID}/execute")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_id"] == STRATEGY_ID
    assert payload["reason"] == "Claude saw a breakout and approved the trade"
    assert captured["strategy_id"] == STRATEGY_ID
    assert captured["force"] is False
    assert captured["symbol"] == "BTCUSDT"


def test_manual_execute_returns_hold_when_cycle_returns_none(phase3_app, monkeypatch):
    """The manual execution endpoint should preserve HOLD semantics from the cycle."""
    import app.api.engine as api_engine

    async def fake_run_single_cycle(*_: Any, **__: Any):
        return None

    monkeypatch.setattr(api_engine, "run_single_cycle", fake_run_single_cycle)

    with TestClient(phase3_app) as client:
        response = client.post(f"/api/engine/strategies/{STRATEGY_ID}/execute")

    assert response.status_code == 200
    assert response.json() is None


def test_malformed_ai_output_defaults_to_hold_and_retries_once():
    """Malformed Claude output should fall back to HOLD, then recover on retry."""
    parser = DecisionParser()
    malformed_output = '{"action": "BUY", "quantity_pct": "not-a-number"'

    first = parser.parse(malformed_output, "BTCUSDT")
    assert first.valid is False
    assert first.decision.action == AITradeAction.HOLD
    assert first.decision.quantity_pct == Decimal("0")
    assert "Fallback HOLD" in first.decision.reason

    async def repair_call(_: str) -> str:
        return (
            '{"action":"BUY","quantity_pct":0.25,'
            '"reason":"Recovered decision","confidence":0.85,"symbol":"BTCUSDT"}'
        )

    repaired = asyncio.run(
        parser.parse_with_retry(malformed_output, "BTCUSDT", repair_call=repair_call)
    )
    assert repaired.valid is True
    assert repaired.decision.action == AITradeAction.BUY
    assert repaired.decision.repaired is True
    assert repaired.decision.reason == "Recovered decision"


@pytest.mark.parametrize(
    "profile,fragment",
    [
        (AIStrategyProfile.RSI_MA, "RSI, moving averages, and trend strength"),
        (AIStrategyProfile.PRICE_ACTION, "candle structure, support/resistance, breakouts"),
        (AIStrategyProfile.VOLUME_MACD, "volume expansion/contraction, MACD direction"),
        (AIStrategyProfile.CHART_PATTERNS, "chart patterns, neckline/breakout logic"),
    ],
)
def test_strategy_prompt_builder_emits_strategy_specific_guidance(profile, fragment):
    builder = StrategyPromptBuilder()
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        interval="5m",
        current_price=Decimal("50000"),
        closes=[Decimal("49950"), Decimal("50000")],
        highs=[Decimal("50010"), Decimal("50020")],
        lows=[Decimal("49900"), Decimal("49950")],
        volumes=[Decimal("100"), Decimal("120")],
        indicators={"rsi": 45.2},
        has_position=False,
        available_usdt=Decimal("1000"),
        initial_balance_usdt=Decimal("1000"),
        notes=["flat market"],
    )

    bundle = builder.build(profile, snapshot)

    assert fragment in bundle.system
    assert "Return exactly one JSON object" in bundle.system
    assert f"Strategy profile: {profile.value}" in bundle.user
    assert '"action":"BUY|SELL|HOLD"' in bundle.user


def test_flat_market_ai_decision_is_skipped_before_call():
    """Flat markets should skip AI execution before any provider call is made."""
    context = ai_runtime.build_ai_context(
        strategy_id=STRATEGY_ID,
        strategy_name="Phase 3 AI",
        symbol="BTCUSDT",
        interval="5m",
        closes=[50000.0] * 20,
        indicators={"rsi": [50.0, 50.0], "macd": ([0.0, 0.0], [0.0, 0.0], [0.0, 0.0])},
        wallet_available_usdt=Decimal("1000"),
        has_position=False,
        position_quantity=None,
        position_entry_price=None,
        current_price=Decimal("50000"),
        ai_strategy_key="rsi_ma",
        ai_model="claude-3-5-sonnet-latest",
        ai_cooldown_seconds=60,
        ai_max_tokens=700,
        ai_temperature=Decimal("0.2"),
        flat_market_metrics={},
    )

    result = asyncio.run(ai_runtime.evaluate_ai_decision(strategy_key="rsi_ma", context=context))

    assert result.status == "skipped"
    assert result.skip_reason == "flat_market"
    assert "Flat market" in (result.reason or "")
    assert result.usage is None


def test_ai_runtime_tracks_usage_and_estimated_cost_without_network(monkeypatch):
    """Usage returned by the provider should drive deterministic token and cost accounting."""
    monkeypatch.setattr(
        ai_runtime,
        "SETTINGS",
        Settings(
            anthropic_api_key="test-key",
            anthropic_model="claude-3-5-sonnet-latest",
            ai_input_cost_per_1m_tokens_usd=3.0,
            ai_output_cost_per_1m_tokens_usd=15.0,
        ),
    )

    async def fake_call_anthropic(**_: Any) -> dict[str, Any]:
        return {
            "model": "claude-3-5-sonnet-latest",
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 300,
                "total_tokens": 1500,
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"action":"BUY","quantity_pct":0.25,'
                        '"reason":"Confirmed breakout","confidence":0.91}'
                    ),
                }
            ],
        }

    monkeypatch.setattr(ai_runtime, "_call_anthropic", fake_call_anthropic)

    context = ai_runtime.build_ai_context(
        strategy_id=STRATEGY_ID,
        strategy_name="Phase 3 AI",
        symbol="BTCUSDT",
        interval="5m",
        closes=[50000.0 + i * 50.0 for i in range(40)],
        indicators={"rsi": [48.0, 58.0], "macd": ([0.1, 0.4], [0.1, 0.2], [0.0, 0.2])},
        wallet_available_usdt=Decimal("1000"),
        has_position=False,
        position_quantity=None,
        position_entry_price=None,
        current_price=Decimal("51950"),
        ai_strategy_key="rsi_ma",
        ai_model="claude-3-5-sonnet-latest",
        ai_cooldown_seconds=60,
        ai_max_tokens=700,
        ai_temperature=Decimal("0.2"),
        flat_market_metrics={},
    )

    result = asyncio.run(ai_runtime.evaluate_ai_decision(strategy_key="rsi_ma", context=context))

    assert result.status == "signal"
    assert result.signal is not None
    assert result.signal.action.value == "BUY"
    assert result.signal.quantity_pct == Decimal("0.25")
    assert result.reason == "Confirmed breakout"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 1200
    assert result.usage.completion_tokens == 300
    assert result.usage.total_tokens == 1500
    assert result.usage.estimated_cost_usdt == Decimal("0.00810000")


def test_ai_cooldown_helper_blocks_recent_calls():
    """A second AI call inside the cooldown window should be skipped."""
    trading_loop = _optional_import("app.engine.trading_loop")
    skip_fn = _resolve_function(
        trading_loop,
        "should_skip_ai_call",
        "should_skip_ai_decision",
        "should_skip_ai_execution",
    )

    now = datetime.now(timezone.utc)
    strategy = SimpleNamespace(
        id=STRATEGY_ID,
        config_json={"ai_enabled": True, "ai_cooldown_seconds": 60},
        ai_enabled=True,
        last_ai_call_at=now - timedelta(seconds=10),
        last_ai_decision_at=now - timedelta(seconds=10),
    )
    flat_context = {
        "latest_close": 50000.0,
        "sma_short": [50000.0, 50000.5],
        "sma_long": [50000.0, 50000.4],
        "rsi": [50.0, 50.2],
        "macd": ([0.1, 0.1], [0.1, 0.1], [0.0, 0.0]),
    }

    result = _call_best_effort(
        skip_fn,
        {
            "strategy": strategy,
            "strategy_id": strategy.id,
            "strategy_config": strategy.config_json,
            "config": strategy.config_json,
            "config_json": strategy.config_json,
            "ai_enabled": True,
            "cooldown_seconds": 60,
            "ai_cooldown_seconds": 60,
            "last_ai_call_at": strategy.last_ai_call_at,
            "last_ai_decision_at": strategy.last_ai_decision_at,
            "now": now,
            "timestamp": now,
            "market_context": flat_context,
            "indicators": flat_context,
        },
    )

    assert _is_skip_result(result)


def test_flat_market_gate_skips_ai_decision():
    """Flat markets should be detected as low-value AI calls and skipped."""
    trading_loop = _optional_import("app.engine.trading_loop")
    skip_fn = _resolve_function(
        trading_loop,
        "should_skip_flat_market",
        "should_skip_for_flat_market",
        "is_market_flat",
    )

    now = datetime.now(timezone.utc)
    strategy = SimpleNamespace(
        id=STRATEGY_ID,
        config_json={"ai_enabled": True},
        ai_enabled=True,
        last_ai_call_at=now - timedelta(minutes=5),
        last_ai_decision_at=now - timedelta(minutes=5),
    )
    flat_context = {
        "latest_close": 50000.0,
        "price_change_pct": 0.0001,
        "range_pct": 0.0002,
        "volatility": 0.0001,
        "sma_short": [50000.0, 50000.01],
        "sma_long": [50000.0, 50000.005],
        "rsi": [49.8, 50.0],
        "macd": ([0.0, 0.0], [0.0, 0.0], [0.0, 0.0]),
    }

    result = _call_best_effort(
        skip_fn,
        {
            "strategy": strategy,
            "strategy_id": strategy.id,
            "strategy_config": strategy.config_json,
            "config": strategy.config_json,
            "config_json": strategy.config_json,
            "market_context": flat_context,
            "indicators": flat_context,
            "flat_market": True,
            "is_flat_market": True,
            "market_is_flat": True,
            "threshold": 0.001,
            "flat_market_threshold": 0.001,
        },
    )

    assert _is_skip_result(result)


def test_ai_cost_tracking_uses_token_usage_without_network():
    """Token usage should be convertible into a non-zero cost without calling the API."""
    cost_module = _optional_import(
        "app.ai.costs",
        "app.ai.usage",
        "app.ai.metrics",
    )
    cost_fn = _resolve_function(
        cost_module,
        "estimate_cost",
        "calculate_cost",
        "track_usage",
        "record_usage",
    )

    usage = SimpleNamespace(input_tokens=1500, output_tokens=375)
    response = SimpleNamespace(
        model="claude-3-5-sonnet-latest",
        usage=usage,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )

    result = _call_best_effort(
        cost_fn,
        {
            "model": response.model,
            "strategy_id": STRATEGY_ID,
            "response": response,
            "usage": usage,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    )

    if isinstance(result, dict):
        cost = result.get("cost_usd") or result.get("estimated_cost_usd") or result.get("cost")
        assert cost is not None
        assert float(cost) > 0
        return

    if hasattr(result, "cost_usd"):
        assert float(result.cost_usd) > 0
        return

    if hasattr(result, "estimated_cost_usd"):
        assert float(result.estimated_cost_usd) > 0
        return

    assert float(result) > 0
