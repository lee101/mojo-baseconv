"""Analytic tests for the base-conversion kernels.

The upstream `baseconv` 0.1a distribution has no downloadable files left on PyPI
and its repository is gone, so there is nothing to compare against. Every test
here is therefore an identity that must hold for any correct radix transform:
the closed-form value of a digit string, agreement with Python's own arbitrary
precision integers, and round trips through every documented view. The
documented API itself comes from the package's PyPI long description, and the
worked examples in that description are asserted verbatim.

Base conversion is exact integer work, so every comparison is equality and no
tolerance is used.
"""

import random

import pytest

import mojo_baseconv as bc
from mojo_baseconv import _lib

BASES = [
    bc.DECIMAL,
    bc.BINARY,
    bc.OCTAL,
    bc.HEXADECIMAL,
    bc.ALPHA_LOWER,
    bc.ALPHA_UPPER,
    bc.ALPHA,
]


def _reference(digits, base):
    """The definition, spelled out with Python's integers."""
    total = 0
    for digit in digits:
        total = total * base + digit
    return total


# -- the worked examples from the package's own documentation --------------


def test_documented_binary_example():
    num = bc.BINARY("1010011010")
    assert num.decimal == 666
    num.decimal = 423
    assert repr(num) == "Number(BINARY, '110100111')"
    assert num.decimal == 423
    num.base = bc.HEXADECIMAL
    assert repr(num) == "Number(HEXADECIMAL, '1A7')"
    assert str(num) == "0x1A7"
    assert num.values == "1A7"
    num.values = "FFC0DE"
    assert num.decimal == 0xFFC0DE
    assert num.indices == [15, 15, 12, 0, 13, 14]
    num.indices = [1, 10, 7]
    assert repr(num) == "Number(HEXADECIMAL, '1A7')"
    assert num.decimal == 0x1A7


def test_documented_bases_exist_with_the_expected_alphabets():
    assert bc.DECIMAL.words == "0123456789"
    assert bc.BINARY.words == "01"
    assert bc.OCTAL.words == "01234567"
    assert bc.HEXADECIMAL.words == "0123456789ABCDEF"
    assert bc.ALPHA_LOWER.words == "abcdefghijklmnopqrstuvwxyz"
    assert bc.ALPHA_UPPER.words == "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    assert bc.ALPHA.words == bc.ALPHA_LOWER.words + bc.ALPHA_UPPER.words
    for base in BASES:
        assert base.radix == len(base.words)
        assert len(set(base.words)) == base.radix
        assert base.radix >= 2


def test_a_base_is_callable_as_shorthand():
    assert repr(bc.DECIMAL("42")) == repr(bc.Number(bc.DECIMAL, "42"))
    assert bc.HEXADECIMAL("1A7").decimal == 423
    assert bc.DECIMAL().decimal == 0


# -- the kernels against the definition ------------------------------------


@pytest.mark.parametrize("base", BASES, ids=lambda b: b.name)
def test_digit_vectors_match_the_closed_form(base):
    rng = random.Random(20260926)
    for _ in range(60):
        n = rng.randrange(1, 40)
        digits = [rng.randrange(base.radix) for _ in range(n)]
        num = bc.Number(base)
        num.indices = digits
        assert num.decimal == _reference(digits, base.radix)


@pytest.mark.parametrize("base", BASES, ids=lambda b: b.name)
def test_round_trip_through_every_view(base):
    rng = random.Random(11)
    for _ in range(60):
        value = rng.randrange(0, 1 << rng.randrange(1, 400))
        num = bc.Number(base)
        num.decimal = value
        assert num.decimal == value
        assert int(num) == value
        assert bc.Number(base, num.values).decimal == value
        assert bc.Number(base, "".join(base.words[d] for d in num.indices)).decimal == value
        other = bc.Number(base)
        other.base = base
        other.decimal = value
        assert other.decimal == num.decimal


def test_python_int_is_the_reference_for_the_upper_range():
    """Python's arbitrary precision integers are the oracle here.

    Values above 2**64 are the point of the port; a kernel that truncated to a
    machine word would agree with Python on everything smaller.
    """
    for exponent in (1, 32, 63, 64, 65, 127, 128, 512, 1024, 4096):
        value = (1 << exponent) - 1
        num = bc.Number(bc.DECIMAL)
        num.decimal = value
        assert num.decimal == value
        hexed = bc.Number(bc.HEXADECIMAL)
        hexed.decimal = value
        assert bc.Number(bc.HEXADECIMAL, hexed.values).decimal == value
        assert len(hexed.values) == max(1, (value.bit_length() + 3) // 4)


def test_known_powers_and_boundaries():
    assert bc.Number(bc.BINARY, "1" * 64).decimal == 2**64 - 1
    assert bc.Number(bc.DECIMAL, "1" + "0" * 40).decimal == 10**40
    assert bc.HEXADECIMAL("F" * 16).decimal == 16**16 - 1
    assert bc.OCTAL("777").decimal == 511
    # ALPHA is lower-case then upper-case, so 'z' is 25 and 'A' is 26.
    assert bc.ALPHA("zA").decimal == 25 * 52 + 26
    assert bc.Number(bc.DECIMAL, "0").decimal == 0
    assert bc.Number(bc.DECIMAL, "").decimal == 0


def test_leading_zeros_are_stripped_but_zero_survives():
    assert bc.Number(bc.BINARY, "0000101").values == "101"
    assert bc.Number(bc.BINARY, "0000101").decimal == 5
    assert bc.Number(bc.BINARY, "0").values == "0"
    assert bc.Number(bc.DECIMAL, "").values == "0"
    assert bc.Number(bc.DECIMAL, "000").values == "0"
    assert bc.Number(bc.DECIMAL, "000").decimal == 0


def test_string_prefixes():
    assert str(bc.Number(bc.HEXADECIMAL, "1A7")) == "0x1A7"
    assert str(bc.Number(bc.OCTAL, "777")) == "0o777"
    assert str(bc.Number(bc.BINARY, "1010")) == "0b1010"
    assert str(bc.Number(bc.DECIMAL, "42")) == "42"
    assert str(bc.Number(bc.ALPHA, "zA")) == "zA"
    assert str(bc.Number(bc.DECIMAL, "0")) == "0"


def test_setting_a_base_converts_rather_than_reinterprets():
    num = bc.Number(bc.DECIMAL, "255")
    assert num.decimal == 255
    num.base = bc.HEXADECIMAL
    assert num.values == "FF"
    assert num.decimal == 255
    num.base = bc.BINARY
    assert len(num.values) == 8
    assert num.decimal == 255


# -- error paths ------------------------------------------------------------


def test_a_symbol_outside_the_base_is_rejected():
    with pytest.raises(ValueError):
        bc.Number(bc.DECIMAL, "12A")
    with pytest.raises(ValueError):
        bc.Number(bc.BINARY, "12")


def test_an_index_outside_the_base_is_rejected():
    num = bc.Number(bc.OCTAL)
    with pytest.raises(ValueError):
        num.indices = [0, 8]
    with pytest.raises(ValueError):
        num.indices = [0, -1]


def test_negative_and_non_integer_values_are_rejected():
    num = bc.Number(bc.DECIMAL)
    with pytest.raises(ValueError):
        num.decimal = -1
    with pytest.raises(TypeError):
        num.values = 42
    with pytest.raises(TypeError):
        num.base = "DECIMAL"
    with pytest.raises(TypeError):
        bc.Number("DECIMAL", "1")


def test_a_base_needs_two_distinct_symbols():
    with pytest.raises(ValueError):
        bc.Base("X", "a")
    with pytest.raises(ValueError):
        bc.Base("X", "aa")


def test_digits_to_int_rejects_an_impossible_base():
    """Inferring the radix from the digits would make `[0]` a radix-1 number.

    The base is passed explicitly for exactly that reason, and a caller who
    supplies a bad one gets an error rather than a division by zero.
    """
    with pytest.raises(ValueError):
        _lib.digits_to_int([0], 1)
    with pytest.raises(ValueError):
        bc.DECIMAL("1").base = bc.Base("BAD", "0")
    with pytest.raises(ValueError):
        _lib.digits_to_int([0, 5], 2)


# -- kernel level -----------------------------------------------------------


def test_chunk_width_keeps_the_packed_chunk_inside_64_bits():
    for radix in (2, 3, 8, 10, 16, 36, 58, 62, 256):
        width = _lib.chunk_width(radix)
        assert radix**width < 2**32
        assert width == 6 or radix ** (width + 1) >= 2**32


def test_zero_value_writes_no_digits():
    assert _lib.int_to_digits(0, 10) == []
    assert _lib.digits_to_int([], 10) == 0


@pytest.mark.parametrize("radix", [2, 3, 7, 10, 16, 36, 52, 58, 62])
def test_kernels_agree_with_each_other_on_random_digits(radix):
    rng = random.Random(radix)
    for _ in range(40):
        n = rng.randrange(1, 60)
        digits = [rng.randrange(radix) for _ in range(n)]
        got = _lib.digits_to_int(digits, radix)
        assert got == _reference(digits, radix)
        assert _lib.int_to_digits(got, radix) == _strip(digits)


def _strip(digits):
    """Leading zeros dropped; the kernel writes nothing at all for zero."""
    start = 0
    while start < len(digits) and digits[start] == 0:
        start += 1
    return digits[start:]


def test_large_digit_vectors_round_trip():
    rng = random.Random(99)
    digits = [rng.randrange(58) for _ in range(2000)]
    value = _lib.digits_to_int(digits, 58)
    assert value == _reference(digits, 58)
    assert _lib.int_to_digits(value, 58) == _strip(digits)
