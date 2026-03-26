"""API router for AI call logs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db_session
from app.engine.ai_runtime import MODEL_PRICING
from app.models.ai_call_log import AICallLog
from app.models.strategy import Strategy

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-logs", tags=["ai-logs"])


@router.get("")
async def list_ai_logs(
    strategy_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    query = select(AICallLog).order_by(AICallLog.created_at.desc())
    count_query = select(func.count()).select_from(AICallLog)

    if strategy_id:
        query = query.where(AICallLog.strategy_id == strategy_id)
        count_query = count_query.where(AICallLog.strategy_id == strategy_id)
    if status:
        query = query.where(AICallLog.status == status)
        count_query = count_query.where(AICallLog.status == status)

    total = (await session.execute(count_query)).scalar() or 0
    result = await session.execute(query.offset(offset).limit(limit))
    logs = result.scalars().all()

    # Get strategy names for display
    strategy_ids = {log.strategy_id for log in logs}
    strategy_names: dict[str, str] = {}
    if strategy_ids:
        strats = await session.execute(
            select(Strategy.id, Strategy.name).where(Strategy.id.in_(strategy_ids))
        )
        strategy_names = {row.id: row.name for row in strats}

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "logs": [
            {
                "id": log.id,
                "strategy_id": log.strategy_id,
                "strategy_name": strategy_names.get(log.strategy_id, "Unknown"),
                "symbol": log.symbol,
                "status": log.status,
                "skip_reason": log.skip_reason,
                "action": log.action,
                "confidence": float(log.confidence) if log.confidence is not None else None,
                "reasoning": log.reasoning,
                "error": log.error,
                "provider": log.provider,
                "model": log.model,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "total_tokens": log.total_tokens,
                "cost_usdt": float(log.cost_usdt),
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@router.get("/stats")
async def ai_log_stats(
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    total = (await session.execute(select(func.count()).select_from(AICallLog))).scalar() or 0
    success = (await session.execute(
        select(func.count()).select_from(AICallLog).where(
            AICallLog.status.in_(["success", "signal", "hold"])
        )
    )).scalar() or 0
    skipped = (await session.execute(
        select(func.count()).select_from(AICallLog).where(AICallLog.status == "skipped")
    )).scalar() or 0
    errors = (await session.execute(
        select(func.count()).select_from(AICallLog).where(AICallLog.status == "error")
    )).scalar() or 0
    total_cost = (await session.execute(
        select(func.sum(AICallLog.cost_usdt))
    )).scalar() or 0
    total_tokens_used = (await session.execute(
        select(func.sum(AICallLog.total_tokens))
    )).scalar() or 0

    return {
        "total_calls": total,
        "success": success,
        "skipped": skipped,
        "errors": errors,
        "total_cost_usdt": float(total_cost),
        "total_tokens": total_tokens_used,
    }


@router.get("/pricing")
async def ai_pricing() -> dict:
    """Return the model pricing table used for cost estimation."""
    return {
        model: {"input_per_1m": rates[0], "output_per_1m": rates[1]}
        for model, rates in sorted(MODEL_PRICING.items())
    }


async def _resolve_api_key_id(
    client: httpx.AsyncClient,
    admin_key: str,
    api_key: str,
) -> tuple[str | None, str | None, str | None]:
    """Find the key_id and project_id for the configured OPENAI_API_KEY.

    Walks all projects and their keys, matching by the last 4 chars of the
    redacted value (OpenAI redacts the middle but exposes the suffix).
    """
    if not api_key:
        return None, None, None

    key_suffix = api_key[-4:]

    resp, error = await _safe_admin_get(
        client,
        "https://api.openai.com/v1/organization/projects",
        params={"limit": 100},
        headers={"Authorization": f"Bearer {admin_key}"},
        operation="list projects",
    )
    if resp is None:
        return None, None, error
    if resp.status_code != 200:
        return None, None, _http_status_error(resp)

    last_error: str | None = None
    for project in resp.json().get("data", []):
        pid = project["id"]
        keys_resp, error = await _safe_admin_get(
            client,
            f"https://api.openai.com/v1/organization/projects/{pid}/api_keys",
            params={"limit": 100},
            headers={"Authorization": f"Bearer {admin_key}"},
            operation=f"list api keys for project {pid}",
        )
        if keys_resp is None:
            last_error = error
            continue
        if keys_resp.status_code != 200:
            last_error = _http_status_error(keys_resp)
            continue
        for key in keys_resp.json().get("data", []):
            redacted = key.get("redacted_value", "")
            if redacted.endswith(key_suffix):
                return key["id"], pid, None

    return None, None, last_error


def _http_status_error(response: httpx.Response) -> str:
    return f"{response.status_code}: {response.text[:200]}"


def _transport_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return f"request timed out ({exc.__class__.__name__})"

    detail = str(exc).strip()
    if detail:
        return f"{exc.__class__.__name__}: {detail}"
    return exc.__class__.__name__


async def _safe_admin_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict,
    headers: dict[str, str],
    operation: str,
) -> tuple[httpx.Response | None, str | None]:
    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("openai admin api request failed operation=%s error=%s", operation, exc)
        return None, _transport_error_message(exc)

    return response, None


@router.get("/openai-usage")
async def openai_usage(
    days: int = Query(7, ge=1, le=90),
) -> dict:
    """Fetch real usage data from OpenAI Admin API, filtered to this project's API key.

    Requires OPENAI_ADMIN_KEY env var (admin key from
    https://platform.openai.com/settings/organization/admin-keys).
    """
    settings = get_settings()
    admin_key = settings.openai_admin_key
    if not admin_key:
        return {
            "error": "OPENAI_ADMIN_KEY not configured. "
                     "Create one at https://platform.openai.com/settings/organization/admin-keys "
                     "and set it in your .env file.",
            "configured": False,
        }

    now = datetime.now(timezone.utc)
    start_time = int((now - timedelta(days=days)).timestamp())
    auth = {"Authorization": f"Bearer {admin_key}"}
    timeout = httpx.Timeout(20.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Resolve which key_id and project_id belong to this app's API key
        api_key_id, project_id, lookup_error = await _resolve_api_key_id(
            client, admin_key, settings.openai_api_key,
        )

        # --- Costs (filter by project_id since costs API doesn't support api_key_id) ---
        costs_params: dict = {"start_time": start_time, "bucket_width": "1d"}
        if project_id:
            costs_params["project_ids"] = [project_id]

        # --- Usage (filter by api_key_id for exact key-level filtering) ---
        usage_params: dict = {
            "start_time": start_time,
            "bucket_width": "1d",
            "group_by": ["model"],
        }
        if api_key_id:
            usage_params["api_key_ids"] = [api_key_id]
        (costs_resp, costs_error), (usage_resp, usage_error) = await asyncio.gather(
            _safe_admin_get(
                client,
                "https://api.openai.com/v1/organization/costs",
                params=costs_params,
                headers=auth,
                operation="fetch costs",
            ),
            _safe_admin_get(
                client,
                "https://api.openai.com/v1/organization/usage/completions",
                params=usage_params,
                headers=auth,
                operation="fetch usage",
            ),
        )

    result: dict = {
        "configured": True,
        "days": days,
        "api_key_id": api_key_id,
        "project_id": project_id,
        "filtered": bool(api_key_id or project_id),
    }
    if lookup_error:
        result["lookup_error"] = lookup_error

    if costs_resp is not None and costs_resp.status_code == 200:
        costs_data = costs_resp.json()
        buckets = costs_data.get("data", [])
        total_usd = 0.0
        daily_costs = []
        for bucket in buckets:
            day_usd = 0.0
            for r in bucket.get("results", []):
                amount_str = r.get("amount", {}).get("value", "0")
                day_usd += float(amount_str)
            total_usd += day_usd
            daily_costs.append({
                "date": datetime.fromtimestamp(bucket["start_time"], tz=timezone.utc).strftime("%Y-%m-%d"),
                "cost_usd": round(day_usd, 6),
            })
        result["costs"] = {
            "total_usd": round(total_usd, 6),
            "daily": daily_costs,
        }
    elif costs_resp is not None:
        result["costs_error"] = _http_status_error(costs_resp)
    elif costs_error:
        result["costs_error"] = costs_error
    else:
        result["costs_error"] = "request failed"

    if usage_resp is not None and usage_resp.status_code == 200:
        usage_data = usage_resp.json()
        buckets = usage_data.get("data", [])
        total_input = 0
        total_output = 0
        total_requests = 0
        model_breakdown: dict[str, dict] = {}
        for bucket in buckets:
            for r in bucket.get("results", []):
                model = r.get("model") or "unknown"
                inp = r.get("input_tokens", 0)
                out = r.get("output_tokens", 0)
                reqs = r.get("num_model_requests", 0)
                total_input += inp
                total_output += out
                total_requests += reqs
                if model not in model_breakdown:
                    model_breakdown[model] = {"input_tokens": 0, "output_tokens": 0, "requests": 0}
                model_breakdown[model]["input_tokens"] += inp
                model_breakdown[model]["output_tokens"] += out
                model_breakdown[model]["requests"] += reqs
        result["usage"] = {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_requests": total_requests,
            "by_model": model_breakdown,
        }
    elif usage_resp is not None:
        result["usage_error"] = _http_status_error(usage_resp)
    elif usage_error:
        result["usage_error"] = usage_error
    else:
        result["usage_error"] = "request failed"

    return result
