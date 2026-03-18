from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Mapping

import httpx


@dataclass
class AnthropicClientConfig:
    api_key: str
    model: str = "claude-3-5-sonnet-latest"
    base_url: str = "https://api.anthropic.com"
    api_version: str = "2023-06-01"
    timeout_seconds: float = 60.0
    max_tokens: int = 1024
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    min_interval_seconds: float = 0.0
    max_concurrency: int | None = None


@dataclass
class AnthropicUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AnthropicMessageResult:
    content: str
    model: str
    stop_reason: str | None = None
    usage: AnthropicUsage = field(default_factory=AnthropicUsage)
    raw: dict[str, Any] = field(default_factory=dict)


class _CallGate:
    def __init__(self, min_interval_seconds: float = 0.0, max_concurrency: int | None = None) -> None:
        self._min_interval_seconds = max(0.0, min_interval_seconds)
        self._last_started = 0.0
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency else None

    @asynccontextmanager
    async def acquire(self):
        if self._semaphore is not None:
            await self._semaphore.acquire()
        try:
            if self._min_interval_seconds > 0:
                async with self._lock:
                    now = monotonic()
                    wait_for = self._last_started + self._min_interval_seconds - now
                    if wait_for > 0:
                        await asyncio.sleep(wait_for)
                    self._last_started = monotonic()
            yield
        finally:
            if self._semaphore is not None:
                self._semaphore.release()


class AsyncAnthropicClient:
    """Small Anthropic-compatible client with retry and throttle support."""

    def __init__(
        self,
        config: AnthropicClientConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = http_client or httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )
        self._owns_client = http_client is None
        self._gate = _CallGate(
            min_interval_seconds=config.min_interval_seconds,
            max_concurrency=config.max_concurrency,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "AsyncAnthropicClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def messages(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        extra_headers: Mapping[str, str] | None = None,
        extra_body: Mapping[str, Any] | None = None,
    ) -> AnthropicMessageResult:
        payload: dict[str, Any] = {
            "model": model or self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": temperature,
        }
        if extra_body:
            payload.update(extra_body)

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.config.api_version,
            "content-type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with self._gate.acquire():
                    response = await self._client.post(
                        "/v1/messages",
                        headers=headers,
                        json=payload,
                    )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError(
                        "retryable response from Anthropic",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                data = response.json()
                return self._parse_message_response(data)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(self.config.retry_backoff_seconds * (2**attempt))

        assert last_error is not None
        raise last_error

    def _parse_message_response(self, data: dict[str, Any]) -> AnthropicMessageResult:
        content = data.get("content", [])
        if isinstance(content, list):
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            text = "".join(text_parts)
        else:
            text = str(content)

        usage_data = data.get("usage", {}) or {}
        usage = AnthropicUsage(
            input_tokens=int(usage_data.get("input_tokens", 0) or 0),
            output_tokens=int(usage_data.get("output_tokens", 0) or 0),
            total_tokens=int(usage_data.get("input_tokens", 0) or 0)
            + int(usage_data.get("output_tokens", 0) or 0),
        )

        return AnthropicMessageResult(
            content=text,
            model=str(data.get("model", self.config.model)),
            stop_reason=data.get("stop_reason"),
            usage=usage,
            raw=data,
        )
