"""`evaluate(expr)`: a safe arithmetic evaluator (no `eval`), shared by the verify stage
and the `expression_input` grader (so it lives in `content`, which both may import).

It accepts integers and decimal-comma numbers ("2,5"), `+`, `-`/`−`, `×`/`x`/`X`/`*`/
`\\times`, `:`/`/`/`÷`, parentheses and unary minus, and returns an exact `Fraction`.
Anything else (words, `[[slot]]` markers, `\\frac`, dots) gives None, as does division by
zero or an expression that is too long or too deeply nested. With `dot_decimal=True` a `.`
is also accepted as the decimal separator ("3.5"), for a child's free-typed input.
"""

from __future__ import annotations

import re
import unicodedata
from fractions import Fraction

MAX_TOKENS = 200
MAX_CHARS = 500
MAX_DEPTH = 32

_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:,\d+)?)|(?P<op>\\times|[+\-−×xX*:/÷()]))",
)
_TOKEN_DOT = re.compile(
    r"\s*(?:(?P<num>\d+(?:[,.]\d+)?)|(?P<op>\\times|[+\-−×xX*:/÷()]))",
)
_OPS = {
    "+": "+",
    "-": "-",
    "−": "-",
    "×": "*",
    "x": "*",
    "X": "*",
    "*": "*",
    "\\times": "*",
    ":": "/",
    "/": "/",
    "÷": "/",
    "(": "(",
    ")": ")",
}


class _Fail(Exception):
    pass


def _tokens(text: str, pattern: re.Pattern[str]) -> list[str | Fraction] | None:
    tokens: list[str | Fraction] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        match = pattern.match(text, pos)
        if match is None:
            return None
        pos = match.end()
        if match.group("num") is not None:
            tokens.append(Fraction(match.group("num").replace(",", ".")))
        else:
            tokens.append(_OPS[match.group("op")])
        if len(tokens) > MAX_TOKENS:
            return None
    return tokens


class _Parser:
    def __init__(self, tokens: list[str | Fraction]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | Fraction | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str | Fraction:
        token = self.peek()
        if token is None:
            raise _Fail
        self.pos += 1
        return token

    def expr(self, depth: int) -> Fraction:
        if depth > MAX_DEPTH:
            raise _Fail
        value = self.term(depth)
        while self.peek() in ("+", "-"):
            op = self.take()
            right = self.term(depth)
            value = value + right if op == "+" else value - right
        return value

    def term(self, depth: int) -> Fraction:
        value = self.factor(depth)
        while self.peek() in ("*", "/"):
            op = self.take()
            right = self.factor(depth)
            if op == "*":
                value *= right
            elif right == 0:
                raise _Fail
            else:
                value /= right
        return value

    def factor(self, depth: int) -> Fraction:
        token = self.take()
        if isinstance(token, Fraction):
            return token
        if token == "-":
            if depth > MAX_DEPTH:
                raise _Fail
            return -self.factor(depth + 1)
        if token == "(":
            value = self.expr(depth + 1)
            if self.take() != ")":
                raise _Fail
            return value
        raise _Fail


def evaluate(expr: str, *, dot_decimal: bool = False) -> Fraction | None:
    """The exact value of an arithmetic expression, or None when it is not one."""
    if not isinstance(expr, str) or len(expr) > MAX_CHARS:
        return None
    tokens = _tokens(unicodedata.normalize("NFC", expr), _TOKEN_DOT if dot_decimal else _TOKEN)
    if not tokens:
        return None
    parser = _Parser(tokens)
    try:
        value = parser.expr(0)
    except _Fail:
        return None
    return value if parser.pos == len(tokens) else None


def format_number(value: Fraction) -> str:
    """A Fraction as a canonical numeric string ("7", "2,5", "-3"); a non-terminating
    fraction is written "a/b"."""
    if value.denominator == 1:
        return str(value.numerator)
    d = value.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d != 1:
        return f"{value.numerator}/{value.denominator}"
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole = value.numerator // value.denominator
    rest = value - whole
    digits = ""
    while rest:
        rest *= 10
        digit = rest.numerator // rest.denominator
        digits += str(digit)
        rest -= digit
    return f"{sign}{whole},{digits}"
