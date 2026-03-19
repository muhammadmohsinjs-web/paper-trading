import logging

from app.logging_utils import AccessConsoleFormatter, PrettyConsoleFormatter


def test_pretty_console_formatter_compacts_backend_records() -> None:
    formatter = PrettyConsoleFormatter(use_color=False)
    record = logging.LogRecord(
        name="app.engine.trading_loop",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="trade executed strategy_id=%s action=%s",
        args=("abc123", "BUY"),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert "INF" in rendered
    assert "engine.loop" in rendered
    assert "trade executed strategy_id=abc123 action=BUY" in rendered
    assert "\033[" not in rendered


def test_access_console_formatter_normalizes_uvicorn_access_records() -> None:
    formatter = AccessConsoleFormatter(use_color=False)
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=24,
        msg='%s - "%s %s HTTP/%s" %s',
        args=("127.0.0.1:50844", "GET", "/api/health", "1.1", 200),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert "GET /api/health" in rendered
    assert "status=200" in rendered
    assert "client=127.0.0.1:50844" in rendered
    assert "http/1.1" in rendered
