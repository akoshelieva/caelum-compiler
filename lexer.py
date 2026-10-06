"""Hand-written byte-oriented lexer for Caelum.

The lexer intentionally does not use regular expressions, str.split(), or a
lexer generator. It walks the UTF-8 source byte-by-byte and recognizes the
non-ASCII language symbols from their exact UTF-8 byte sequences.
"""

from enum import Enum, auto

from errors import CompilationError
from tokens import Token, TokenKind


class LexerState(Enum):
    START = auto()
    IDENTIFIER = auto()
    INTEGER = auto()


_KEYWORDS = {
    "fixed": TokenKind.FIXED,
    "calm": TokenKind.CALM,
    "flow": TokenKind.FLOW,
    "when": TokenKind.WHEN,
    "otherwise": TokenKind.OTHERWISE,
    "light": TokenKind.LIGHT,
    "dark": TokenKind.DARK,
}

_SYMBOLS = (
    ("☁︎".encode("utf-8"), TokenKind.TYPE_BOOL, "☁︎"),
    ("☼".encode("utf-8"), TokenKind.TYPE_I32, "☼"),
    ("☽".encode("utf-8"), TokenKind.TYPE_I64, "☽"),
    ("⟨".encode("utf-8"), TokenKind.BLOCK_OPEN, "⟨"),
    ("⟩".encode("utf-8"), TokenKind.BLOCK_CLOSE, "⟩"),
)


class Lexer:
    def __init__(self, source: bytes) -> None:
        self.source = source
        self.position = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        state = LexerState.START

        while self.position < len(self.source):
            if state is LexerState.START:
                byte = self.source[self.position]

                if self._is_whitespace(byte):
                    self._advance_ascii(byte)
                    continue

                symbol = self._match_symbol()
                if symbol is not None:
                    symbol_bytes, kind, text = symbol
                    tokens.append(Token(kind, text, self.line, self.column))
                    self._advance_symbol(len(symbol_bytes))
                    continue

                start_line = self.line
                start_column = self.column

                if self._is_letter(byte):
                    state = LexerState.IDENTIFIER
                    start = self.position
                    while self.position < len(self.source) and self._is_letter(
                        self.source[self.position]
                    ):
                        self._advance_ascii(self.source[self.position])
                    text = self.source[start:self.position].decode("ascii")
                    kind = _KEYWORDS.get(text, TokenKind.IDENTIFIER)
                    tokens.append(Token(kind, text, start_line, start_column))
                    state = LexerState.START
                    continue

                if self._is_digit(byte):
                    state = LexerState.INTEGER
                    start = self.position
                    while self.position < len(self.source) and self._is_digit(
                        self.source[self.position]
                    ):
                        self._advance_ascii(self.source[self.position])
                    text = self.source[start:self.position].decode("ascii")
                    tokens.append(
                        Token(TokenKind.INTEGER, text, start_line, start_column)
                    )
                    state = LexerState.START
                    continue

                if byte == ord("="):
                    if self._peek_byte(1) == ord("="):
                        tokens.append(
                            Token(TokenKind.EQUAL, "==", start_line, start_column)
                        )
                        self._advance_ascii(byte)
                        self._advance_ascii(ord("="))
                    else:
                        tokens.append(
                            Token(TokenKind.ASSIGN, "=", start_line, start_column)
                        )
                        self._advance_ascii(byte)
                    continue

                if byte == ord("!") and self._peek_byte(1) == ord("="):
                    tokens.append(
                        Token(TokenKind.NOT_EQUAL, "!=", start_line, start_column)
                    )
                    self._advance_ascii(byte)
                    self._advance_ascii(ord("="))
                    continue

                if byte == ord("-"):
                    tokens.append(
                        Token(TokenKind.MINUS, "-", start_line, start_column)
                    )
                    self._advance_ascii(byte)
                    continue

                if byte == ord("."):
                    tokens.append(Token(TokenKind.DOT, ".", start_line, start_column))
                    self._advance_ascii(byte)
                    continue

                self._raise_unexpected_byte(byte)

        tokens.append(Token(TokenKind.EOF, "", self.line, self.column))
        return tokens

    def _match_symbol(self):
        for symbol in _SYMBOLS:
            symbol_bytes = symbol[0]
            if self.source.startswith(symbol_bytes, self.position):
                return symbol
        return None

    def _peek_byte(self, offset: int) -> int | None:
        index = self.position + offset
        if index >= len(self.source):
            return None
        return self.source[index]

    @staticmethod
    def _is_letter(byte: int) -> bool:
        return ord("A") <= byte <= ord("Z") or ord("a") <= byte <= ord("z")

    @staticmethod
    def _is_digit(byte: int) -> bool:
        return ord("0") <= byte <= ord("9")

    @staticmethod
    def _is_whitespace(byte: int) -> bool:
        return byte in (ord(" "), ord("\t"), ord("\r"), ord("\n"))

    def _advance_ascii(self, byte: int) -> None:
        self.position += 1
        if byte == ord("\n"):
            self.line += 1
            self.column = 1
        else:
            self.column += 1

    def _advance_symbol(self, byte_count: int) -> None:
        self.position += byte_count
        self.column += 1

    def _raise_unexpected_byte(self, byte: int) -> None:
        if 32 <= byte <= 126:
            display = chr(byte)
            message = f"unexpected character '{display}'"
        else:
            message = f"unexpected byte 0x{byte:02X}"
        raise CompilationError(self.line, self.column, message)
