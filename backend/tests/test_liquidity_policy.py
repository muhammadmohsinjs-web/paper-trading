from decimal import Decimal

from app.engine.liquidity_policy import (
    LIQUIDITY_ARCHETYPE_MAJOR,
    LIQUIDITY_ARCHETYPE_MEME,
    LIQUIDITY_ARCHETYPE_MID,
    LIQUIDITY_ARCHETYPE_SMALL,
    build_liquidity_policy,
    infer_liquidity_archetype,
)


def test_infer_liquidity_archetype_detects_major_and_meme_bases():
    assert infer_liquidity_archetype("BTCUSDT", observed_volume_24h_usdt=80_000_000.0) == LIQUIDITY_ARCHETYPE_MAJOR
    assert infer_liquidity_archetype("WIFUSDT", observed_volume_24h_usdt=20_000_000.0) == LIQUIDITY_ARCHETYPE_MEME


def test_infer_liquidity_archetype_uses_volume_tiers_for_alts():
    assert infer_liquidity_archetype("LINKUSDT", observed_volume_24h_usdt=12_000_000.0) == LIQUIDITY_ARCHETYPE_MID
    assert infer_liquidity_archetype("RENDERUSDT", observed_volume_24h_usdt=4_500_000.0) == LIQUIDITY_ARCHETYPE_SMALL


def test_build_liquidity_policy_scales_by_archetype_and_notional():
    meme_policy = build_liquidity_policy(
        "WIFUSDT",
        observed_volume_24h_usdt=5_000_000.0,
    )
    small_policy = build_liquidity_policy(
        "RENDERUSDT",
        observed_volume_24h_usdt=5_000_000.0,
    )
    execution_policy = build_liquidity_policy(
        "RENDERUSDT",
        observed_volume_24h_usdt=5_000_000.0,
        estimated_notional=Decimal("2000"),
    )

    assert meme_policy.required_24h_volume_usdt == 8_000_000.0
    assert small_policy.required_24h_volume_usdt == 1_000_000.0
    assert small_policy.discovery_floor_usdt == 750_000.0
    assert execution_policy.required_24h_volume_usdt == 1_000_000.0
    assert execution_policy.interval_hard_floor_usdt > 0.0
