"""Correctness-gated benchmark for mojo-baseconv.

There is no upstream distribution left to benchmark against, so the reference is
CPython's own arbitrary-precision integer, which is the fastest reasonable
implementation of the same computation: `int(str_value, radix)` for the digit
string to integer direction and a `while` loop of `divmod` for the other. Every
case checks the result against Python's integer before timing.
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python"))

import mojo_baseconv as bc  # noqa: E402
from mojo_baseconv import _lib  # noqa: E402

# Radix 16 so that `int(text, radix)` is a legal CPython conversion and the
# reference is the C implementation rather than a Python-level divmod chain.
RADIX = 16
WORDS = "0123456789ABCDEF"
BASE = bc.Base("HEX", WORDS)


def _time(fn, repeats=5):
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def _python_digits(value: int, radix: int) -> str:
    if value == 0:
        return "0"
    out = []
    while value:
        value, digit = divmod(value, radix)
        out.append(WORDS[digit])
    return "".join(reversed(out))


def bench_to_int(ndigits: int, repeats: int):
    """Digit string to unbounded integer: Python's int(str, radix) or the kernel."""
    value = (1 << (ndigits * 4)) - 1
    text = _python_digits(value, RADIX)
    digits = [WORDS.index(c) for c in text]
    assert _lib.digits_to_int(digits, RADIX) == int(text, RADIX) == value

    return (
        f"digits->int {ndigits}",
        _time(lambda: int(text, RADIX), repeats),
        _time(lambda: _lib.digits_to_int(digits, RADIX), repeats),
    )


def bench_to_digits(nbits: int, repeats: int):
    """Unbounded integer to digit string: a divmod chain or the kernel."""
    value = (1 << nbits) - 1
    assert _python_digits(value, RADIX) == "".join(
        WORDS[d] for d in _lib.int_to_digits(value, RADIX)
    )

    return (
        f"int->digits {nbits}b",
        _time(lambda: _python_digits(value, RADIX), repeats),
        _time(lambda: _lib.int_to_digits(value, RADIX), repeats),
    )


def bench_number_round_trip(nbits: int, repeats: int):
    """The `Number` object: set decimal, read values and indices back."""
    value = (1 << nbits) - 1
    num = bc.Number(BASE)
    num.decimal = value
    assert num.decimal == value

    return (
        f"Number round trip {nbits}b",
        _time(lambda: _python_digits(value, RADIX), repeats),
        _time(lambda: _lib.int_to_digits(value, RADIX), repeats),
    )


def main():
    plan = [(10, 2000), (40, 1000), (160, 400), (640, 150), (2560, 60), (10240, 20)]
    print(f"{'case':<24}{'python int':>14}{'mojo-baseconv':>16}{'ratio':>9}")
    print("-" * 63)
    for count, repeats in plan:
        for label, ref, ours in (
            bench_to_int(count, repeats),
            bench_to_digits(count * 4, repeats),
        ):
            print(f"{label:<24}{ref*1e6:>12.2f}us{ours*1e6:>14.2f}us{ref/ours:>8.2f}x")
    print()
    print("The reference is CPython's arbitrary-precision int, which is already")
    print("C. A Python-level divmod chain over a byte string would be a strawman.")


if __name__ == "__main__":
    main()
