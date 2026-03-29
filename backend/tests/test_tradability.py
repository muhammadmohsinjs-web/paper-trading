from app.engine.tradability import split_tradability_reason_codes


def test_split_tradability_reason_codes_separates_blocking_from_advisory():
    blocking, advisory = split_tradability_reason_codes(
        [
            "MARKET_QUALITY_TOO_LOW",
            "MOVE_BELOW_COST",
            "NEAR_PEG_PROFILE",
            "LIQUIDITY_TOO_LOW",
        ]
    )

    assert blocking == ["NEAR_PEG_PROFILE", "LIQUIDITY_TOO_LOW"]
    assert advisory == ["MARKET_QUALITY_TOO_LOW", "MOVE_BELOW_COST"]
