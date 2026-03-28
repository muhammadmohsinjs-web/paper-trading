"""Force-close positions in stablecoin-like symbols and return funds to wallets."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal, init_database
from app.engine.tradability import is_stablecoin_symbol
from app.engine.wallet_manager import get_wallet
from app.models.position import Position
from app.models.trade import Trade
from app.models.wallet import Wallet


async def close_stablecoin_positions(apply_changes: bool) -> int:
    await init_database()

    closed = 0
    async with SessionLocal() as session:
        positions = (await session.execute(select(Position))).scalars().all()

        for pos in positions:
            if not is_stablecoin_symbol(pos.symbol):
                continue

            wallet = await get_wallet(session, pos.strategy_id)

            if wallet is None:
                print(f"  SKIP {pos.symbol} — no wallet for strategy {pos.strategy_id}")
                continue

            credit_amount = pos.quantity * pos.entry_price
            pnl = Decimal("0") - (pos.entry_fee or Decimal("0"))
            balance_before = wallet.available_usdt

            # Credit wallet
            wallet.available_usdt += credit_amount
            balance_after = wallet.available_usdt

            # Look up strategy name
            from app.models.strategy import Strategy
            strategy = (
                await session.execute(
                    select(Strategy).where(Strategy.id == pos.strategy_id)
                )
            ).scalar_one_or_none()
            strategy_name = strategy.name if strategy else None

            # Record audit trade
            trade = Trade(
                id=str(uuid4()),
                strategy_id=pos.strategy_id,
                symbol=pos.symbol,
                side="SELL",
                quantity=pos.quantity,
                price=pos.entry_price,
                market_price=pos.entry_price,
                fee=Decimal("0"),
                slippage=Decimal("0"),
                pnl=pnl,
                pnl_pct=Decimal("0"),
                ai_reasoning="Force-closed stablecoin position (cleanup)",
                executed_at=datetime.now(timezone.utc),
                decision_source="system_cleanup",
                strategy_name=strategy_name,
                cost_usdt=credit_amount,
                wallet_balance_before=balance_before,
                wallet_balance_after=balance_after,
            )
            session.add(trade)
            await session.delete(pos)
            closed += 1

            print(
                f"  CLOSE {pos.symbol}: qty={float(pos.quantity):.4f} "
                f"credit=${float(credit_amount):.2f} "
                f"wallet={float(balance_before):.2f} -> {float(balance_after):.2f}"
            )

        if apply_changes:
            await session.commit()
            print(f"\nApplied: {closed} stablecoin position(s) closed.")
        else:
            await session.rollback()
            print(f"\nDry run: {closed} stablecoin position(s) would be closed. Use --apply to execute.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Force-close positions in stablecoin/pegged symbols.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the changes. Without this flag the script runs as a dry run.",
    )
    args = parser.parse_args()
    return asyncio.run(close_stablecoin_positions(apply_changes=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
