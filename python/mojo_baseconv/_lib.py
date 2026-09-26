"""ctypes bridge to the compiled base-conversion kernels.

The shared library owns no memory. Every buffer crosses the C ABI as a 64-bit
address, so the argtypes below must stay `c_int64` for addresses; `c_int`
truncates them and segfaults. Scratch buffers are allocated here, on the Python
side, which keeps the exported Mojo symbols free of allocation and of `raises`.
"""

from __future__ import annotations

import ctypes
import math
import pathlib

import numpy as np

_HERE = pathlib.Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_LIB_PATH = _ROOT / "dist" / "libmojo-baseconv.so"


def _load():
    if not _LIB_PATH.exists():
        raise RuntimeError(
            f"{_LIB_PATH} not found; run `bash build/build.sh` first"
        )
    lib = ctypes.CDLL(str(_LIB_PATH))
    i = ctypes.c_int64
    lib.bc_digits_to_int.restype = i
    lib.bc_digits_to_int.argtypes = [i, i, i, i, i, i]
    lib.bc_int_to_digits.restype = i
    lib.bc_int_to_digits.argtypes = [i, i, i, i, i]
    lib.bc_chunk_width.restype = i
    lib.bc_chunk_width.argtypes = [i]
    return lib


lib = _load()


def chunk_width(base: int) -> int:
    """Radix digits the Mojo kernel moves per limb pass."""
    return int(lib.bc_chunk_width(ctypes.c_int64(base)))


def digits_to_int(digits, base: int) -> int:
    """Evaluate a most-significant-first digit vector in `base` as an integer.

    The base is explicit rather than inferred from the largest digit: a valid
    digit string may legitimately contain only zeros, and inferring radix 1 from
    `[0]` is not a conversion, it is a division by zero.
    """
    if base < 2:
        raise ValueError("base must be at least 2")
    return _convert([int(d) for d in digits], int(base))


def _convert(values: list[int], base: int) -> int:
    n = len(values)
    if n == 0:
        return 0
    arr = np.array(values, dtype=np.int32)
    bits = int(n * math.log2(max(base, 2))) + 2
    max_limbs = (bits + 31) // 32 + 2
    limbs = np.zeros(max_limbs, dtype=np.uint32)
    slots = np.zeros(1, dtype=np.int32)
    rc = lib.bc_digits_to_int(
        arr.ctypes.data, n, base, limbs.ctypes.data, max_limbs, slots.ctypes.data
    )
    if rc != 0:
        if rc == -1:
            raise RuntimeError("baseconv integer scratch too small")
        raise ValueError(
            "digit {!r} is outside radix {}".format(values[-rc - 2], base)
        )
    used = int(slots[0])
    return int.from_bytes(limbs[:used].tobytes(), "little")


def int_to_digits(value: int, base: int) -> list[int]:
    """Render a non-negative integer as most-significant-first radix digits."""
    if value < 0:
        raise ValueError("negative values have no finite digit representation")
    if value == 0:
        return []
    bits = value.bit_length()
    nlimb = (bits + 31) // 32
    limbs = np.zeros(nlimb, dtype=np.uint32)
    limbs[:] = np.frombuffer(
        value.to_bytes(nlimb * 4, "little"), dtype=np.uint32
    )
    width = chunk_width(base)
    max_digits = int(bits / math.log2(base)) + 2
    out_cap = ((max_digits + width - 1) // width) * width
    out = np.zeros(out_cap, dtype=np.uint8)
    start = lib.bc_int_to_digits(
        limbs.ctypes.data, nlimb, base, out.ctypes.data, out_cap
    )
    if start < 0:
        raise RuntimeError("baseconv digit buffer too small")
    return [int(v) for v in out[start:]]
