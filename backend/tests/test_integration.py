"""Integration test — full cycle: create strategy → execute trade → verify DB."""

import pytest
import pytest_asyncio
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import default_ai_model_for_provider, get_settings
from app.models import Base
from app.market.data_store import Candle, DataStore


@pytest_asyncio.fixture(autouse=True)
async def setup_data_store():
    """Pre-populate the DataStore with enough candle data for indicators."""
    DataStore.reset()
    store = DataStore.get_instance()

    # Generate 200 candles with a clear SMA crossover pattern
    candles = []
    base_price = 50000.0
    for i in range(200):
        # Price goes up, then crosses down at candle 150
        if i < 100:
            price = base_price + i * 10  # uptrend
        elif i < 150:
            price = base_price + 1000 - (i - 100) * 5  # slow decline
        else:
            price = base_price + 750 - (i - 150) * 20  # sharper decline

        candles.append(
            Candle(
                open_time=1700000000000 + i * 300000,
                open=price - 5,
                high=price + 10,
                low=price - 10,
                close=price,
                volume=100.0 + i,
            )
        )
    store.set_candles("BTCUSDT", "5m", candles)
    yield
    DataStore.reset()


@pytest_asyncio.fixture
async def test_app():
    """Create a test app with in-memory DB, bypassing Binance connections."""
    from app.config import get_settings
    from app.database import engine, SessionLocal
    from app.models import Base

    # Create tables on the existing engine (which uses the .env DB)
    # For isolation, we override with in-memory
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Monkey-patch the database module
    import app.database as db_mod
    original_engine = db_mod.engine
    original_session = db_mod.SessionLocal
    db_mod.engine = test_engine
    db_mod.SessionLocal = test_session_factory

    # Also patch the get_db_session
    async def test_get_db():
        async with test_session_factory() as session:
            yield session

    from app.main import create_app
    app = create_app()

    # Override the dependency
    from app.database import get_db_session
    app.dependency_overrides[get_db_session] = test_get_db

    yield app

    # Restore
    db_mod.engine = original_engine
    db_mod.SessionLocal = original_session
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_full_cycle(test_app):
    """Integration: create strategy → check stats → manual execute."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a strategy
        resp = await client.post(
            "/api/strategies",
            json={
                "name": "Test SMA",
                "description": "Integration test strategy",
                "config_json": {
                    "strategy_type": "sma_crossover",
                    "sma_short": 10,
                    "sma_long": 50,
                    "initial_balance": 1000,
                },
                "is_active": True,
            },
        )
        assert resp.status_code == 201, resp.text
        strategy = resp.json()
        strategy_id = strategy["id"]
        assert strategy["name"] == "Test SMA"
        assert strategy["is_active"] is True

        # 2. List strategies
        resp = await client.get("/api/strategies")
        assert resp.status_code == 200
        strategies = resp.json()
        assert len(strategies) >= 1

        # 3. Get strategy detail
        resp = await client.get(f"/api/strategies/{strategy_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["available_usdt"] == 1000.0

        # 4. Check market price endpoint
        resp = await client.get("/api/market/price/BTCUSDT")
        assert resp.status_code == 200
        assert "price" in resp.json()

        # 5. Check candles endpoint
        resp = await client.get("/api/market/candles/BTCUSDT?interval=5m&limit=50")
        assert resp.status_code == 200
        candle_data = resp.json()
        assert candle_data["count"] == 50

        # 6. Manual execute
        resp = await client.post(f"/api/engine/strategies/{strategy_id}/execute")
        assert resp.status_code == 200

        # 7. Get trade history
        resp = await client.get(f"/api/strategies/{strategy_id}/trades")
        assert resp.status_code == 200

        # 8. Trade summary
        resp = await client.get(f"/api/strategies/{strategy_id}/trades/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert "total_trades" in summary

        # 9. Dashboard
        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        dash = resp.json()
        assert dash["total_strategies"] >= 1

        # 10. Leaderboard
        resp = await client.get("/api/dashboard/leaderboard")
        assert resp.status_code == 200

        # 11. Engine status
        resp = await client.get("/api/engine/status")
        assert resp.status_code == 200

        # 12. Health check
        resp = await client.get("/api/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_strategy_crud(test_app):
    """Test create, read, update, delete flow."""
    settings = get_settings()
    expected_provider = settings.ai_provider
    expected_model = default_ai_model_for_provider(expected_provider, settings)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create
        resp = await client.post(
            "/api/strategies",
            json={"name": "CRUD Test", "config_json": {}, "ai_provider": "openai", "ai_model": "ignored-model"},
        )
        assert resp.status_code == 201
        created = resp.json()
        sid = created["id"]
        assert created["ai_provider"] == expected_provider
        assert created["ai_model"] == expected_model

        # Read
        resp = await client.get(f"/api/strategies/{sid}")
        assert resp.status_code == 200

        # Update
        resp = await client.patch(
            f"/api/strategies/{sid}",
            json={"name": "Updated Name", "ai_provider": "openai", "ai_model": "still-ignored"},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "Updated Name"
        assert updated["ai_provider"] == expected_provider
        assert updated["ai_model"] == expected_model

        # Delete
        resp = await client.delete(f"/api/strategies/{sid}")
        assert resp.status_code == 204

        # Verify deleted
        resp = await client.get(f"/api/strategies/{sid}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_active_strategy_clamps_loop_interval_to_candle_interval(test_app, monkeypatch):
    """Creating an active strategy should not start a loop faster than its candle interval."""
    captured: list[tuple[str, int]] = []

    import app.api.strategies as strategies_api

    class DummyManager:
        async def start_strategy(self, strategy_id: str, interval_seconds: int = 3600) -> bool:
            captured.append((strategy_id, interval_seconds))
            return True

    dummy_manager = DummyManager()
    monkeypatch.setattr(
        strategies_api.StrategyManager,
        "get_instance",
        classmethod(lambda cls: dummy_manager),
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/strategies",
            json={
                "name": "Hybrid Interval Clamp",
                "config_json": {
                    "strategy_type": "hybrid_composite",
                    "interval_seconds": 300,
                    "initial_balance": 1000,
                },
                "candle_interval": "1h",
                "is_active": True,
            },
        )

    assert resp.status_code == 201, resp.text
    assert len(captured) == 1
    assert captured[0][1] == 3600


@pytest.mark.asyncio
async def test_activate_strategy_clamps_loop_interval_to_candle_interval(test_app, monkeypatch):
    """Activating an existing strategy should respect the candle interval floor."""
    captured: list[tuple[str, int]] = []

    import app.api.strategies as strategies_api

    class DummyManager:
        async def start_strategy(self, strategy_id: str, interval_seconds: int = 3600) -> bool:
            captured.append((strategy_id, interval_seconds))
            return True

        async def stop_strategy(self, strategy_id: str) -> bool:
            return True

    dummy_manager = DummyManager()
    monkeypatch.setattr(
        strategies_api.StrategyManager,
        "get_instance",
        classmethod(lambda cls: dummy_manager),
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/strategies",
            json={
                "name": "Toggle Interval Clamp",
                "config_json": {
                    "strategy_type": "hybrid_composite",
                    "interval_seconds": 300,
                    "initial_balance": 1000,
                },
                "candle_interval": "1h",
                "is_active": False,
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        strategy_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/strategies/{strategy_id}",
            json={"is_active": True},
        )

    assert resp.status_code == 200, resp.text
    assert len(captured) == 1
    assert captured[0][0] == strategy_id
    assert captured[0][1] == 3600
