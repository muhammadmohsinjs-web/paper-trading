import httpx
import pytest

from app.api import ai_logs
from app.config import Settings


def _response(url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, json=payload, request=request)


class TimeoutOnCostsClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, params=None, headers=None) -> httpx.Response:
        request = httpx.Request("GET", url, params=params, headers=headers)
        if url.endswith("/organization/projects"):
            return _response(url, {"data": [{"id": "proj_1"}]})
        if url.endswith("/api_keys"):
            return _response(
                url,
                {"data": [{"id": "key_1", "redacted_value": "sk-proj-1234"}]},
            )
        if url.endswith("/organization/costs"):
            raise httpx.ReadTimeout("timed out", request=request)
        if url.endswith("/organization/usage/completions"):
            return _response(
                url,
                {
                    "data": [
                        {
                            "start_time": 1_710_000_000,
                            "results": [
                                {
                                    "model": "gpt-5.4-mini",
                                    "input_tokens": 100,
                                    "output_tokens": 20,
                                    "num_model_requests": 2,
                                }
                            ],
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {url}")


class TimeoutOnLookupClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, params=None, headers=None) -> httpx.Response:
        request = httpx.Request("GET", url, params=params, headers=headers)
        if url.endswith("/organization/projects"):
            raise httpx.ReadTimeout("timed out", request=request)
        if url.endswith("/organization/costs"):
            return _response(
                url,
                {
                    "data": [
                        {
                            "start_time": 1_710_000_000,
                            "results": [{"amount": {"value": "1.25"}}],
                        }
                    ]
                },
            )
        if url.endswith("/organization/usage/completions"):
            return _response(
                url,
                {
                    "data": [
                        {
                            "start_time": 1_710_000_000,
                            "results": [
                                {
                                    "model": "gpt-5.4-mini",
                                    "input_tokens": 50,
                                    "output_tokens": 10,
                                    "num_model_requests": 1,
                                }
                            ],
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {url}")


@pytest.mark.asyncio
async def test_openai_usage_returns_partial_data_when_costs_times_out(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_logs,
        "get_settings",
        lambda: Settings(openai_admin_key="admin-key", openai_api_key="sk-live-1234"),
    )
    monkeypatch.setattr(ai_logs.httpx, "AsyncClient", TimeoutOnCostsClient)

    result = await ai_logs.openai_usage(days=7)

    assert result["configured"] is True
    assert result["filtered"] is True
    assert "costs_error" in result
    assert "timed out" in result["costs_error"]
    assert result["usage"]["total_input_tokens"] == 100
    assert result["usage"]["total_output_tokens"] == 20
    assert result["usage"]["total_requests"] == 2


@pytest.mark.asyncio
async def test_openai_usage_falls_back_to_unfiltered_data_when_lookup_times_out(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_logs,
        "get_settings",
        lambda: Settings(openai_admin_key="admin-key", openai_api_key="sk-live-1234"),
    )
    monkeypatch.setattr(ai_logs.httpx, "AsyncClient", TimeoutOnLookupClient)

    result = await ai_logs.openai_usage(days=7)

    assert result["configured"] is True
    assert result["filtered"] is False
    assert "lookup_error" in result
    assert "timed out" in result["lookup_error"]
    assert result["costs"]["total_usd"] == 1.25
    assert result["usage"]["total_requests"] == 1
