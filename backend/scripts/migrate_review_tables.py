#!/usr/bin/env python3
"""
One-shot migration: creates review_ledger and review_forward_outcomes tables.

Run on the VM:
    cd /path/to/paper-trading/backend
    python scripts/migrate_review_tables.py

Safe to run multiple times — all statements use CREATE TABLE IF NOT EXISTS
and CREATE INDEX IF NOT EXISTS.
"""

import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "paper_trading.db"


def main() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to {DB_PATH} ...")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")

    stmts = [
        # ── review_ledger ─────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS review_ledger (
            id                        VARCHAR(36) PRIMARY KEY,
            strategy_id               VARCHAR(36) NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            cycle_id                  VARCHAR(36) NOT NULL,
            cycle_ts                  DATETIME,
            symbol                    VARCHAR(24) NOT NULL,
            interval                  VARCHAR(8),
            in_universe               BOOLEAN NOT NULL DEFAULT 0,
            tradability_pass          BOOLEAN,
            data_sufficient           BOOLEAN,
            setup_detected            BOOLEAN,
            setup_type                VARCHAR(64),
            setup_family              VARCHAR(32),
            liquidity_pass            BOOLEAN,
            final_gate_pass           BOOLEAN NOT NULL DEFAULT 0,
            rejection_stage           VARCHAR(64),
            rejection_reason_code     VARCHAR(64),
            rejection_reason_text     TEXT,
            daily_pick_rank           INTEGER,
            scanner_score             FLOAT,
            regime_at_decision        VARCHAR(48),
            regime_fit_score          FLOAT,
            setup_fit_score           FLOAT,
            universe_size             INTEGER,
            rank_among_qualified      INTEGER,
            ai_called                 BOOLEAN NOT NULL DEFAULT 0,
            ai_action                 VARCHAR(16),
            ai_confidence             FLOAT,
            ai_status                 VARCHAR(32),
            ai_cost_usdt              FLOAT,
            ai_reasoning_snippet      TEXT,
            trade_opened              BOOLEAN NOT NULL DEFAULT 0,
            entry_price               FLOAT,
            market_price_at_entry     FLOAT,
            slippage_pct              FLOAT,
            entry_fee_usdt            FLOAT,
            position_size_usdt        FLOAT,
            wallet_balance_before_usdt FLOAT,
            exposure_pct              FLOAT,
            composite_score           FLOAT,
            entry_confidence          FLOAT,
            confidence_bucket         VARCHAR(16),
            indicator_snapshot        JSON,
            decision_source           VARCHAR(32),
            no_execute_reason         VARCHAR(64),
            trade_closed              BOOLEAN NOT NULL DEFAULT 0,
            exit_price                FLOAT,
            exit_fee_usdt             FLOAT,
            realized_pnl_usdt         FLOAT,
            realized_pnl_pct          FLOAT,
            exit_reason               VARCHAR(32),
            hold_duration_candles     FLOAT,
            hold_duration_hours       FLOAT,
            position_still_open       BOOLEAN NOT NULL DEFAULT 0,
            outcome_bucket            VARCHAR(32),
            root_cause                VARCHAR(32),
            root_cause_confidence     VARCHAR(8),
            created_at                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, cycle_id, symbol)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_review_ledger_strategy_id   ON review_ledger(strategy_id)",
        "CREATE INDEX IF NOT EXISTS ix_review_ledger_cycle_id       ON review_ledger(cycle_id)",
        "CREATE INDEX IF NOT EXISTS ix_review_ledger_symbol         ON review_ledger(symbol)",
        "CREATE INDEX IF NOT EXISTS ix_review_ledger_cycle_ts       ON review_ledger(cycle_ts)",
        "CREATE INDEX IF NOT EXISTS ix_review_ledger_outcome_bucket ON review_ledger(outcome_bucket)",
        "CREATE INDEX IF NOT EXISTS ix_review_ledger_root_cause     ON review_ledger(root_cause)",

        # ── review_forward_outcomes ───────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS review_forward_outcomes (
            id                    VARCHAR(36) PRIMARY KEY,
            ledger_id             VARCHAR(36) NOT NULL REFERENCES review_ledger(id) ON DELETE CASCADE,
            symbol                VARCHAR(24) NOT NULL,
            decision_ts           DATETIME,
            decision_price        FLOAT,
            interval              VARCHAR(8),
            fwd_ret_1             FLOAT,
            fwd_ret_4             FLOAT,
            fwd_ret_12            FLOAT,
            fwd_ret_24            FLOAT,
            fwd_max_favorable_pct FLOAT,
            fwd_max_adverse_pct   FLOAT,
            fwd_data_available    BOOLEAN NOT NULL DEFAULT 0,
            computed_at           DATETIME,
            created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ledger_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_review_forward_outcomes_ledger_id ON review_forward_outcomes(ledger_id)",
        "CREATE INDEX IF NOT EXISTS ix_review_forward_outcomes_symbol     ON review_forward_outcomes(symbol)",
    ]

    with con:
        for stmt in stmts:
            con.execute(stmt)

    # Verify
    tables = {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    for expected in ("review_ledger", "review_forward_outcomes"):
        status = "OK" if expected in tables else "MISSING"
        print(f"  {expected}: {status}")

    con.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
