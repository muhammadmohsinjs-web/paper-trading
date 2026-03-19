from __future__ import annotations

import logging
import logging.config
import os
import sys
from datetime import datetime

ANSI_RESET = "\033[0m"
ANSI_DIM = "\033[2m"
ANSI_BLUE = "\033[94m"
ANSI_CYAN = "\033[96m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"
ANSI_MAGENTA = "\033[95m"

LOGGER_ALIASES = {
    "app.main": "server",
    "app.api.ws": "api.ws",
    "app.engine.ai_runtime": "engine.ai",
    "app.engine.trading_loop": "engine.loop",
    "app.market.binance_rest": "market.rest",
    "app.market.binance_ws": "market.ws",
    "app.strategies.manager": "strategy.mgr",
}

LEVEL_STYLES = {
    logging.DEBUG: ("DBG", ANSI_BLUE),
    logging.INFO: ("INF", ANSI_CYAN),
    logging.WARNING: ("WRN", ANSI_YELLOW),
    logging.ERROR: ("ERR", ANSI_RED),
    logging.CRITICAL: ("CRT", ANSI_MAGENTA),
}


def _supports_color(enabled: bool) -> bool:
    if not enabled or os.getenv("NO_COLOR"):
        return False
    if os.getenv("TERM", "").lower() == "dumb":
        return False

    for stream in (sys.stderr, sys.stdout):
        if hasattr(stream, "isatty") and stream.isatty():
            return True
    return False


def _colorize(value: str, color: str, *, enabled: bool) -> str:
    if not enabled:
        return value
    return f"{color}{value}{ANSI_RESET}"


def _short_logger_name(name: str) -> str:
    if name in LOGGER_ALIASES:
        return LOGGER_ALIASES[name]

    shortened = name[4:] if name.startswith("app.") else name
    parts = shortened.split(".")
    if len(parts) <= 2:
        return shortened
    return ".".join((*parts[:-1], parts[-1].replace("_", "-")))


def _normalize_level(level_name: str) -> str:
    candidate = (level_name or "INFO").strip().upper()
    try:
        logging._checkLevel(candidate)
    except (TypeError, ValueError):
        return "INFO"
    return candidate


class PrettyConsoleFormatter(logging.Formatter):
    def __init__(self, use_color: bool = True) -> None:
        super().__init__()
        self.use_color = _supports_color(use_color)

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).astimezone().strftime("%H:%M:%S")
        timestamp = f"{timestamp}.{int(record.msecs):03d}"
        level_label, level_color = LEVEL_STYLES.get(record.levelno, ("LOG", ANSI_CYAN))
        logger_name = _short_logger_name(record.name)

        message = record.getMessage()
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            message = f"{message}\n{exc_text}" if message else exc_text
        if record.stack_info:
            stack_text = self.formatStack(record.stack_info)
            message = f"{message}\n{stack_text}" if message else stack_text

        plain_prefix = f"{timestamp} | {level_label:<3} | {logger_name:<12} | "
        color_prefix = (
            f"{_colorize(timestamp, ANSI_DIM, enabled=self.use_color)} | "
            f"{_colorize(f'{level_label:<3}', level_color, enabled=self.use_color)} | "
            f"{_colorize(f'{logger_name:<12}', ANSI_DIM, enabled=self.use_color)} | "
        )

        lines = (message or "").splitlines() or [""]
        indent = " " * len(plain_prefix)
        formatted = [f"{color_prefix}{lines[0]}"]
        formatted.extend(f"{indent}{line}" for line in lines[1:])
        return "\n".join(formatted)


class AccessConsoleFormatter(PrettyConsoleFormatter):
    def format(self, record: logging.LogRecord) -> str:
        access_record = logging.makeLogRecord(record.__dict__.copy())
        if isinstance(access_record.args, tuple) and len(access_record.args) >= 5:
            client_addr, method, full_path, http_version, status_code = access_record.args[:5]
            access_record.msg = (
                f"{method} {full_path} "
                f"status={self._format_status(status_code)} "
                f"client={client_addr} http/{http_version}"
            )
            access_record.args = ()
        return super().format(access_record)

    def _format_status(self, status_code: object) -> str:
        try:
            numeric_status = int(status_code)
        except (TypeError, ValueError):
            return str(status_code)

        if numeric_status >= 500:
            color = ANSI_RED
        elif numeric_status >= 400:
            color = ANSI_YELLOW
        elif numeric_status >= 300:
            color = ANSI_CYAN
        else:
            color = ANSI_GREEN
        return _colorize(str(numeric_status), color, enabled=self.use_color)


def configure_logging(level_name: str = "INFO", *, use_color: bool = True) -> None:
    normalized_level = _normalize_level(level_name)
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "pretty": {
                    "()": "app.logging_utils.PrettyConsoleFormatter",
                    "use_color": use_color,
                },
                "access": {
                    "()": "app.logging_utils.AccessConsoleFormatter",
                    "use_color": use_color,
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "pretty",
                    "stream": "ext://sys.stderr",
                },
                "access": {
                    "class": "logging.StreamHandler",
                    "formatter": "access",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": normalized_level,
                "handlers": ["default"],
            },
            "loggers": {
                "uvicorn": {
                    "level": normalized_level,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": normalized_level,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": normalized_level,
                    "handlers": ["access"],
                    "propagate": False,
                },
                "websockets": {
                    "level": "WARNING",
                    "handlers": ["default"],
                    "propagate": False,
                },
                "httpx": {
                    "level": "WARNING",
                    "handlers": ["default"],
                    "propagate": False,
                },
                "httpcore": {
                    "level": "WARNING",
                    "handlers": ["default"],
                    "propagate": False,
                },
            },
        }
    )
