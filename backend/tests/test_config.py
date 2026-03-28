from app.config import BASE_DIR, _resolve_database_url


def test_resolve_database_url_keeps_absolute_sqlite_url() -> None:
    value = "sqlite+aiosqlite:////tmp/paper_trading.db"
    assert _resolve_database_url(value) == value


def test_resolve_database_url_keeps_memory_sqlite_url() -> None:
    value = "sqlite+aiosqlite:///:memory:"
    assert _resolve_database_url(value) == value


def test_resolve_database_url_expands_relative_sqlite_url() -> None:
    value = "sqlite+aiosqlite:///./paper_trading.db"
    expected = f"sqlite+aiosqlite:///{(BASE_DIR / 'paper_trading.db').resolve()}"
    assert _resolve_database_url(value) == expected


def test_resolve_database_url_expands_relative_sqlite_url_with_query() -> None:
    value = "sqlite:///data/dev.db?mode=rwc"
    expected = f"sqlite:///{(BASE_DIR / 'data/dev.db').resolve()}?mode=rwc"
    assert _resolve_database_url(value) == expected
