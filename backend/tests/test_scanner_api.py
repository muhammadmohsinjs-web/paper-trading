from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_refresh_live_market_data_reloads_active_universe(monkeypatch):
    import app.api.scanner as scanner_api

    calls: list[tuple[str, str, int]] = []

    class DummySelector:
        async def get_active_universe(self, *, force_refresh: bool = False):
            assert force_refresh is True
            return ["BTCUSDT", "ETHUSDT"]

        def get_last_snapshot(self):
            return SimpleNamespace(promoted=["ETHUSDT"], demoted=["SOLUSDT"])

    async def fake_backfill(symbol: str, interval: str, limit: int = 200) -> int:
        calls.append((symbol, interval, limit))
        return 200

    monkeypatch.setattr(
        scanner_api.UniverseSelector,
        "get_instance",
        classmethod(lambda cls: DummySelector()),
    )
    monkeypatch.setattr(scanner_api, "backfill", fake_backfill)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/scanner/live/refresh?limit=150")

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["status"] == "refreshed"
    assert payload["active_universe_size"] == 2
    assert payload["symbols_refreshed"] == 2
    assert payload["intervals_refreshed"] == ["5m", "1h", "4h"]
    assert payload["requested_pairs"] == 6
    assert payload["successful_pairs"] == 6
    assert payload["failed_pairs"] == 0
    assert payload["active_symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert payload["promoted"] == ["ETHUSDT"]
    assert payload["demoted"] == ["SOLUSDT"]
    assert sorted(calls) == sorted(
        [
            ("BTCUSDT", "5m", 150),
            ("BTCUSDT", "1h", 150),
            ("BTCUSDT", "4h", 150),
            ("ETHUSDT", "5m", 150),
            ("ETHUSDT", "1h", 150),
            ("ETHUSDT", "4h", 150),
        ]
    )
