"""Pre-entry revalidation for daily picks.

Checks whether a pick is still valid before the engine commits to entry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.regime.types import DetailedRegime, RegimeResult
from app.scanner.families import FAMILY_ALLOWED_REGIMES, SetupFamily

logger = logging.getLogger(__name__)

# Configurable defaults
DEFAULT_MAX_SIGNAL_AGE_HOURS = 8
DEFAULT_DRIFT_LIMIT_PCT = 3.0


def revalidate_pick(
    *,
    scanner_anchor_price: float | None,
    scanner_signal_ts: datetime | None,
    scanner_family: str | None,
    scanner_detailed_regime: str | None,
    scanner_drift_limit_pct: float | None,
    current_price: float,
    current_regime: RegimeResult | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return (valid, reason) — False means the pick should be skipped.

    Designed to be called from the trading loop before committing to an entry.
    All scanner_* fields may be None for legacy picks (pre-migration) which
    always pass validation.
    """
    current_time = now or datetime.now(timezone.utc)

    # Legacy picks without scanner context always pass
    if scanner_anchor_price is None and scanner_signal_ts is None:
        return True, "Legacy pick — no scanner context"

    # Price drift check
    if scanner_anchor_price is not None and scanner_anchor_price > 0:
        drift_limit = scanner_drift_limit_pct if scanner_drift_limit_pct is not None else DEFAULT_DRIFT_LIMIT_PCT
        drift_pct = abs(current_price - scanner_anchor_price) / scanner_anchor_price * 100
        if drift_pct > drift_limit:
            reason = f"Price drifted {drift_pct:.2f}% from anchor {scanner_anchor_price:.4f} (limit {drift_limit:.1f}%)"
            logger.info("revalidation: SKIP — %s", reason)
            return False, reason

    # Signal age check
    if scanner_signal_ts is not None:
        signal_ts = scanner_signal_ts
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.replace(tzinfo=timezone.utc)
        age = current_time - signal_ts
        max_age = timedelta(hours=DEFAULT_MAX_SIGNAL_AGE_HOURS)
        if age > max_age:
            reason = f"Signal age {age.total_seconds() / 3600:.1f}h exceeds max {DEFAULT_MAX_SIGNAL_AGE_HOURS}h"
            logger.info("revalidation: SKIP — %s", reason)
            return False, reason

    # Regime compatibility check
    if scanner_family and current_regime and current_regime.detailed_regime:
        try:
            family = SetupFamily(scanner_family)
        except ValueError:
            family = None
        if family is not None:
            allowed = FAMILY_ALLOWED_REGIMES.get(family, set())
            if current_regime.detailed_regime not in allowed:
                reason = (
                    f"Current regime {current_regime.detailed_regime.value} "
                    f"not compatible with family {scanner_family}"
                )
                logger.info("revalidation: SKIP — %s", reason)
                return False, reason

    return True, "Pick passed revalidation"
