from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Base


def test_root_and_health_routes() -> None:
    with TestClient(create_app()) as client:
        root_response = client.get("/")
        health_response = client.get("/api/health")

        assert root_response.status_code == 200
        assert root_response.json()["status"] == "ok"
        assert health_response.status_code == 200
        assert health_response.json() == {"status": "ok"}


def test_expected_tables_are_registered() -> None:
    expected_tables = {
        "daily_picks",
        "strategies",
        "wallets",
        "positions",
        "trades",
        "snapshots",
        "price_cache",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))
