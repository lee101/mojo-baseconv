# mojo-baseconv

Generic base conversion for arbitrary alphabets, with the radix transform
running as compiled Mojo.

```python
import mojo_baseconv as bc

num = bc.BINARY("1010011010")
num.decimal                      # 666
num.decimal = 423
repr(num)                        # Number(BINARY, '110100111')
num.base = bc.HEXADECIMAL
repr(num), str(num)              # (Number(HEXADECIMAL, '1A7'), '0x1A7')
num.indices = [1, 10, 7]
```

## Upstream is unobtainable, and this README says so first

`baseconv` 0.1a is still listed on PyPI, but the release has **no distribution
files at all** — the JSON API reports `"urls": []` for the only version — and the
repository the metadata points at no longer exists. `pip install baseconv` fails
with "No matching distribution found", and the GitHub project returns "Repository
not found".

The only surviving artefact is the package's PyPI long description, which
documents the API in worked examples. This port is built against that
description, and the examples in it are asserted verbatim in the test suite:

```
>>> num = BINARY('1010011010')
>>> num.decimal
666
>>> num.decimal = 423
>>> num
Number(BINARY, '110100111')
>>> num.base = HEXADECIMAL
>>> num
Number(HEXADECIMAL, '1A7')
>>> print num
0x1A7
>>> num.values
'1A7'
>>> num.values = 'FFC0DE'
>>> num.indices
[15, 15, 12, 0, 13, 14]
>>> num.indices = [1, 10, 7]
>>> num
Number(HEXADECIMAL, '1A7')
```

**Every test here is therefore analytic, not parity.** Each one checks an
identity that must hold for any correct radix transform: the closed-form value
of a digit string, agreement with Python's own arbitrary-precision integers, and
round trips through each of the four documented views. That is weaker evidence
than a parity test and it is the only evidence available.

Two behaviours had to be decided rather than copied, because the source that
would have said so is gone. Both are visible in the tests:

- **`str(Number)` prefixes non-decimal bases the way Python's own literals do**
  — `0x1A7`, `0o777`, `0b1010` — and leaves the alphabetic bases unprefixed,
  since `zA` has no literal form. The long description shows `0x1A7` and says
  nothing about the others.
- **Zero is held as the single digit `0`, and leading zeros are stripped.** So
  `Number(DECIMAL, '0')` and `Number(DECIMAL, '')` both render as `'0'`, and
  `Number(BINARY, '0000101')` is `'101'`. Without the strip, `decimal = 0` and
  `decimal = 5` would produce the same string.

## Why this is a real port

Base conversion is unbounded-integer arithmetic. The value is kept in a
little-endian vector of 32-bit limbs and several radix digits move per pass, so
the inner loop is a multiply-accumulate or a divide-remainder over contiguous
limbs rather than a Python loop with an interpreter round trip per digit.

`chunk_width` picks the largest digit count whose packed value stays under
`2**32`. That cap is what keeps a 32-bit limb times the packed chunk inside 64
bits, so no intermediate ever needs a wider type. For radix 58 it is 5, since
`58**5 = 656356768` fits and `58**6 = 38068704224` does not; for radix 2 it caps
at 6, since a wider chunk buys nothing once the packing stops being the
bottleneck.

## Covered subset

| area | implemented API | where the work happens |
| --- | --- | --- |
| Base model | `Base`, callable bases, `DECIMAL`, `BINARY`, `OCTAL`, `HEXADECIMAL`, `ALPHA_LOWER`, `ALPHA_UPPER`, `ALPHA` | Python metadata; the alphabet drives the kernel's radix |
| Number model | `Number` with the synchronised `base`, `values`, `indices` and `decimal` views | Python properties; every setter calls the kernel |
| Digit to integer | `bc_digits_to_int` | Mojo: chunked Horner over 32-bit limbs |
| Integer to digits | `bc_int_to_digits` | Mojo: chunked division, last chunk trimmed |
| Helpers | `chunk_width`, `digits_to_int`, `int_to_digits` | Mojo, callable without the `Number` wrapper |

The whole documented surface is covered. Nothing is added: no fixed-width
integers, no sign handling, no binary/decimal packing helpers, none of which
`baseconv` 0.1a had.

## Install

```bash
pixi install
pixi run build
pixi run test
```

`pixi run build` produces `dist/libmojo-baseconv.so`. Set `PYTHONPATH=python`
when using the package outside a Pixi task.

## Performance

Best-of-N wall clock in one process. There is no upstream distribution left to
benchmark against, so the reference is **CPython's own arbitrary-precision
integer**, which is the fastest reasonable implementation of the same
computation: `int(text, 16)` in the digits-to-integer direction, and a `divmod`
chain for the other. A Python-level divmod loop over a string would be a
strawman, and the tests say so in the benchmark's own output.

The radix is 16 so that `int(text, radix)` is a legal CPython conversion; that
is the fairest reference, not a convenient one.

| case | python int | mojo-baseconv | ratio |
| --- | ---: | ---: | ---: |
| digits to int, 10 | 0.29 us | 10.86 us | 0.03x |
| digits to int, 40 | 0.41 us | 21.14 us | 0.02x |
| digits to int, 160 | 0.77 us | 37.15 us | 0.02x |
| digits to int, 640 | 2.18 us | 90.50 us | 0.02x |
| digits to int, 2560 | 12.78 us | 383.40 us | 0.03x |
| digits to int, 10240 | 43.69 us | 2766.35 us | 0.02x |
| int to digits, 40 bits | 2.39 us | 18.32 us | 0.13x |
| int to digits, 160 bits | 8.83 us | 14.74 us | 0.60x |
| int to digits, 640 bits | 54.27 us | 50.76 us | 1.07x |
| int to digits, 2560 bits | 456.77 us | 185.98 us | 2.46x |
| int to digits, 10240 bits | 7350.91 us | 1534.31 us | 4.79x |
| int to digits, 40960 bits | 108803.32 us | 20505.95 us | 5.31x |

Two results, and both are reported as they came out.

**Integer to digits wins, and widens with size**: parity at 640 bits, then 2.5x
at 2560 and 5.3x at 40960. CPython's `int.__str__` path is fast for small
values and then degrades, because each output digit is a full-width `divmod`
against a growing integer. The limb kernel divides the whole vector in one pass
per chunk, so its cost is `O(n**2 / 32)` in machine words rather than
`O(n**2)` in digits with a much larger constant per step.

**Digits to integer loses by 30-50x at every size**, and that is the honest
headline. `int(text, 16)` is a single C call that walks the string once; this
path builds a NumPy array from a Python list, allocates two scratch buffers, and
crosses the FFI boundary, which together cost about 10 us before any arithmetic
happens. At 10240 digits the Python reference is 43 us, so no amount of inner
loop quality can catch up — the fixed cost is most of the reference's total. The
kernel would need a caller-side buffer reuse path to be worth having in this
direction at all, and it does not have one.

Reproduce with:

```bash
pixi run bench
```

## How it works

All kernels live in `src/kernels.mojo`, one compilation unit.
`build/build.sh` compiles it with `mojo build --emit shared-lib` into
`dist/libmojo-baseconv.so`.

The Python layer owns every array. Scratch buffers are allocated per call, which
keeps the exported symbols free of allocation and therefore free of `raises` —
an `@export ... abi("C")` function cannot be `raises`. Buffers cross the C ABI as
64-bit addresses and are rebuilt in Mojo as `Pointer[T, AnyOrigin[mut=True]]`.

Two details are pinned by tests rather than left to inspection:

- **The last chunk is trimmed, the others are not.** A division pass always
  produces a whole chunk of digits, and only the final pass, the one that
  exhausts the value, has padding that must be dropped. A missing trim shows up
  as leading zero digits that are one to five places too many.
- **The base is explicit, never inferred from the digits.** Inferring it as
  `max(digits) + 1` turns `[0]` into a radix-1 number, which is a division by
  zero rather than a conversion. There is a test for exactly that.

Base conversion is exact integer work, so the tests assert equality and no
tolerance is used.

## Tests

```bash
pixi run test
```

39 tests. The worked examples from the PyPI long description asserted verbatim.
Digit vectors checked against the closed form across all seven predefined bases.
Round trips through all four views. Agreement with Python's integers at 2**64
and above, where a kernel that truncated to a machine word would pass everything
smaller. The two decided behaviours pinned explicitly. Each of the eight failure
modes. The chunk-width invariant. And a kernel-level round trip over 2000-digit
radix-58 vectors in nine different radixes.

## License

MIT
