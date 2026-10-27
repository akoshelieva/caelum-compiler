"""Token definitions for the Caelum compiler."""

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    FIXED = auto()
    CALM = auto()
    FLOW = auto()
    WHEN = auto()
    OTHERWISE = auto()
    LIGHT = auto()
    DARK = auto()

    TYPE_I32 = auto()
    TYPE_I64 = auto()
    TYPE_BOOL = auto()

    IDENTIFIER = auto()
    INTEGER = auto()

    ASSIGN = auto()
    EQUAL = auto()
    NOT_EQUAL = auto()
    MINUS = auto()
    DOT = auto()
    BLOCK_OPEN = auto()
    BLOCK_CLOSE = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    line: int
    column: int
