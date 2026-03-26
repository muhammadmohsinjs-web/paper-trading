import pytest
from sqlalchemy import select

from app.engine.evaluation_logging import build_symbol_evaluation_log
from app.models.symbol_evaluation_log import SymbolEvaluationLog
from app.models.strategy import Strategy


@pytest.mark.asyncio
async def test_symbol_evaluation_log_persists_stage_decision(db_session):
    db_session.add(Strategy(id="test-strategy-1", name="Test Strategy", config_json={}))
    await db_session.commit()

    log = build_symbol_evaluation_log(
        strategy_id="test-strategy-1",
        cycle_id="cycle-1",
        symbol="USDCUSDT",
        stage="economic_viability",
        status="rejected",
        reason_code="TP_BELOW_COST_BUFFER",
        reason_text="Target distance does not clear round-trip cost buffer",
        metrics_json={"net_reward_pct": -0.02},
        context_json={"setup_type": "sma_crossover_proximity"},
    )
    db_session.add(log)
    await db_session.commit()

    stored = (
        await db_session.execute(
            select(SymbolEvaluationLog).where(SymbolEvaluationLog.cycle_id == "cycle-1")
        )
    ).scalar_one()

    assert stored.symbol == "USDCUSDT"
    assert stored.stage == "economic_viability"
    assert stored.status == "rejected"
    assert stored.reason_code == "TP_BELOW_COST_BUFFER"
    assert stored.metrics_json["net_reward_pct"] == -0.02
