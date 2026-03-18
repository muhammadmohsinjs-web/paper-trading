from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from app.ai.client import AnthropicMessageResult, AsyncAnthropicClient
from app.ai.parser import DecisionParser, DecisionParseResult
from app.ai.prompts import PromptBundle, StrategyPromptBuilder
from app.ai.types import AIAnalysisResult, AIUsage, AIStrategyProfile, MarketSnapshot


@dataclass
class AIDecisionRequest:
    profile: AIStrategyProfile | str
    snapshot: MarketSnapshot
    model: str | None = None
    max_tokens: int | None = None
    temperature: float = 0.0


class AIDecisionAdvisor:
    """High-level orchestration for prompts, model calls, and JSON parsing."""

    def __init__(
        self,
        client: AsyncAnthropicClient,
        prompt_builder: StrategyPromptBuilder | None = None,
        parser: DecisionParser | None = None,
    ) -> None:
        self._client = client
        self._prompt_builder = prompt_builder or StrategyPromptBuilder()
        self._parser = parser or DecisionParser()

    async def decide(self, request: AIDecisionRequest) -> AIAnalysisResult:
        profile = self._prompt_builder.resolve_profile(request.profile)
        bundle = self._prompt_builder.build(profile, request.snapshot)
        raw_response = await self._client.messages(
            system=bundle.system,
            user=bundle.user,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        parse_result = await self._parser.parse_with_retry(
            raw_response.content,
            default_symbol=request.snapshot.symbol,
            repair_call=self._repair_call(bundle, request),
        )
        return self._build_result(profile, raw_response, parse_result)

    def _repair_call(
        self,
        bundle: PromptBundle,
        request: AIDecisionRequest,
    ) -> Callable[[str], Awaitable[str]]:
        async def _call(prompt: str) -> str:
            repaired = await self._client.messages(
                system=bundle.system,
                user=prompt,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=0.0,
            )
            return repaired.content

        return _call

    def _build_result(
        self,
        profile: AIStrategyProfile,
        raw_response: AnthropicMessageResult,
        parse_result: DecisionParseResult,
    ) -> AIAnalysisResult:
        decision = parse_result.decision
        decision.strategy_profile = profile
        return AIAnalysisResult(
            decision=decision,
            raw_text=raw_response.content,
            usage=AIUsage(
                input_tokens=raw_response.usage.input_tokens,
                output_tokens=raw_response.usage.output_tokens,
                total_tokens=raw_response.usage.total_tokens,
            ),
            model=raw_response.model,
            stop_reason=raw_response.stop_reason,
            repaired=decision.repaired,
            fallback=not parse_result.valid,
        )
