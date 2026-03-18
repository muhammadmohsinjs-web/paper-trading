from enum import Enum


class PositionSide(str, Enum):
    LONG = "LONG"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
