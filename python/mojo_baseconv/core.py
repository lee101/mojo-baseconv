"""Generic base conversion, with the radix transform in Mojo.

`Base` is a named alphabet; `Number` holds one value in one base and keeps its
`values`, `indices` and `decimal` views in step, so setting any one of them
updates the others. That is the whole model, and it is the model the PyPI long
description for `baseconv` 0.1a documents:

    >>> num = BINARY('1010011010')
    >>> num.decimal
    666
    >>> num.decimal = 423
    >>> num
    Number(BINARY, '110100111')
    >>> num.base = HEXADECIMAL
    >>> num
    Number(HEXADECIMAL, '1A7')
    >>> num.indices
    [1, 10, 7]
    >>> num.indices = [1, 10, 7]

Two things had to be decided rather than copied, because the package's source
is gone: `str(Number)` prefixes non-decimal bases the way Python's own literals
do (`0x1A7`, `0o17`, `0b1010`) and leaves the alphabetic bases unprefixed,
because those have no literal form; and zero is held as the single
digit `0`, so `Number(DECIMAL, '0')` and `Number(DECIMAL, '')` both render as
`'0'` rather than as an empty string.
"""

from __future__ import annotations

from . import _lib

__all__ = [
    "ALPHA",
    "ALPHA_LOWER",
    "ALPHA_UPPER",
    "BINARY",
    "DECIMAL",
    "HEXADECIMAL",
    "OCTAL",
    "Base",
    "Number",
]


class Base:
    """A named alphabet of distinct symbols, used most-significant first."""

    def __init__(self, name: str, words: str, prefix: str = "") -> None:
        if len(words) < 2:
            raise ValueError("a base needs at least two symbols")
        if len(set(words)) != len(words):
            raise ValueError("base symbols must be distinct")
        self.name = name
        self.words = words
        self.prefix = prefix
        self.radix = len(words)

    def index(self, symbol: str) -> int:
        position = self.words.find(symbol)
        if position < 0:
            raise ValueError(
                "{!r} is not a symbol of base {}".format(symbol, self.name)
            )
        return position

    def __call__(self, values: str = "") -> "Number":
        """`BINARY('1010')` is shorthand for `Number(BINARY, '1010')`."""
        return Number(self, values)

    def __repr__(self) -> str:
        return "Base({}, {!r})".format(self.name, self.words)


DECIMAL = Base("DECIMAL", "0123456789")
BINARY = Base("BINARY", "01", "0b")
OCTAL = Base("OCTAL", "01234567", "0o")
HEXADECIMAL = Base("HEXADECIMAL", "0123456789ABCDEF", "0x")
ALPHA_LOWER = Base("ALPHA_LOWER", "abcdefghijklmnopqrstuvwxyz")
ALPHA_UPPER = Base("ALPHA_UPPER", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
ALPHA = Base("ALPHA", ALPHA_LOWER.words + ALPHA_UPPER.words)


class Number:
    """One value, held as base-`base` digits with three synchronised views.

    Assigning to any of `base`, `values`, `indices` or `decimal` recomputes the
    other three, which is the behaviour the reference documents and the reason
    the attributes are properties rather than plain fields.
    """

    def __init__(self, base=DECIMAL, values="") -> None:
        if not isinstance(base, Base):
            raise TypeError("base must be a Base instance")
        self._base = base
        self._digits = _strip_leading_zeros(
            _lib.int_to_digits(int(_decimal_of(base, values)), base.radix)
        )

    # -- the four synchronised views -------------------------------------

    @property
    def base(self) -> Base:
        return self._base

    @base.setter
    def base(self, value: Base) -> None:
        if not isinstance(value, Base):
            raise TypeError("base must be a Base instance")
        magnitude = self.decimal
        self._base = value
        self._digits = _strip_leading_zeros(
            _lib.int_to_digits(magnitude, value.radix)
        )

    @property
    def values(self) -> str:
        return "".join(self._base.words[d] for d in self._digits)

    @values.setter
    def values(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("values must be a str")
        self._digits = [
            self._base.index(symbol) for symbol in value
        ]
        if self._digits and max(self._digits) >= self._base.radix:
            raise ValueError("a symbol is outside the base")

    @property
    def indices(self) -> list[int]:
        return list(self._digits)

    @indices.setter
    def indices(self, value) -> None:
        digits = [int(v) for v in value]
        for position, digit in enumerate(digits):
            if digit < 0 or digit >= self._base.radix:
                raise ValueError(
                    "index {!r} at position {} is outside base {}".format(
                        digit, position, self._base.name
                    )
                )
        self._digits = _strip_leading_zeros(digits)

    @property
    def decimal(self) -> int:
        return _lib.digits_to_int(self._digits, self._base.radix)

    @decimal.setter
    def decimal(self, value: int) -> None:
        value = int(value)
        if value < 0:
            raise ValueError("only non-negative values are representable")
        self._digits = _strip_leading_zeros(
            _lib.int_to_digits(value, self._base.radix)
        )

    # -- rendering --------------------------------------------------------

    def __str__(self) -> str:
        text = self.values
        return self._base.prefix + text if text else self._base.prefix + "0"

    def __repr__(self) -> str:
        return "Number({}, {!r})".format(self._base.name, self.values)

    def __int__(self) -> int:
        return self.decimal

    def __eq__(self, other) -> bool:
        if isinstance(other, Number):
            return self.decimal == other.decimal
        if isinstance(other, int):
            return self.decimal == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.decimal)

    def __len__(self) -> int:
        return len(self._digits)


def _strip_leading_zeros(digits: list[int]) -> list[int]:
    """Drop leading zero digits, keeping at least one.

    `Number(BINARY, '000101')` is 5, and rendering it as `'000101'` would make
    `decimal = 0` and `decimal = 5` produce the same string. A single zero digit
    is kept so the empty vector stays reserved for the number zero itself.
    """
    start = 0
    while start < len(digits) - 1 and digits[start] == 0:
        start += 1
    return digits[start:] or [0]


def _decimal_of(base: Base, values: str) -> int:
    if not isinstance(values, str):
        raise TypeError("values must be a str")
    if not values:
        return 0
    digits = [base.index(symbol) for symbol in values]
    return _lib.digits_to_int(digits, base.radix)
