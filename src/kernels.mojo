"""Arbitrary-base digit conversion in compiled Mojo.

The numeric core of a base-conversion library is one operation: re-expressing
an unbounded integer in a different radix. Both directions keep the value in a
little-endian vector of 32-bit limbs and move several radix digits per pass, so
the inner loop is a multiply-accumulate (digits to integer) or a
divide-remainder (integer to digits) over contiguous limbs.

`chunk_width` picks the largest digit count whose packed value stays under
2**32, which is what keeps a 32-bit limb times the packed chunk inside 64 bits
with no wider intermediate. For radix 58 that is 5 digits, since 58**5 =
656356768 fits and 58**6 = 38068704224 does not; for radix 2 it is capped, since
a wider chunk buys nothing once the packing stops being the bottleneck.

Scratch memory is supplied by the caller. The kernels allocate nothing, which
keeps the exported symbols free of `raises` and lets the Python layer own every
buffer, as the FFI contract requires.

Buffers cross the C ABI as 64-bit addresses and are rebuilt here, because
`@export` rejects a function with an inferred parameter type.
"""

comptime BPtr = Pointer[UInt8, AnyOrigin[mut=True]]
comptime I32 = Pointer[Int32, AnyOrigin[mut=True]]
comptime U32 = Pointer[UInt32, AnyOrigin[mut=True]]

comptime TWO32 = 4294967296
comptime MAX_CHUNK = 6


def bu8(addr: Int) -> BPtr:
    return BPtr(unsafe_from_address=addr)


def bi32(addr: Int) -> I32:
    return I32(unsafe_from_address=addr)


def bu32(addr: Int) -> U32:
    return U32(unsafe_from_address=addr)


def bpow(base: Int, k: Int) -> UInt64:
    """Return base**k; every k the callers use keeps the result under 2**32."""
    var r = UInt64(1)
    var b = UInt64(base)
    for _ in range(k):
        r = r * b
    return r


def chunk_width(base: Int) -> Int:
    """Largest number of radix-`base` digits whose packed value stays under 2**32.

    Capping the packed value at 2**32 is what keeps a 32-bit limb times the
    packed chunk inside 64 bits, so no intermediate ever needs a wider type.
    """
    if base < 2:
        return 1
    var m = UInt64(1)
    var k = 0
    for _ in range(MAX_CHUNK):
        if m * UInt64(base) >= UInt64(TWO32):
            break
        m = m * UInt64(base)
        k += 1
    if k == 0:
        return 1
    return k


@export("bc_digits_to_int")
def bc_digits_to_int(digits_addr: Int, n: Int, base: Int, limb_addr: Int,
                     max_limbs: Int, nlimb_addr: Int) abi("C") -> Int:
    """Evaluate sum(digit[i] * base**(n-1-i)) into 32-bit limbs.

    `digits` holds one radix value per element, most significant first, with -1
    marking an absent value so an invalid digit is caught rather than read as a
    large unsigned number. Returns 0 on success, -(2 + i) for an invalid digit
    at index `i`, -1 if the scratch is too small, and writes the number of limbs
    actually used to `nlimb_addr`.
    """
    if base < 2:
        return -1
    var slots = bi32(nlimb_addr)
    slots[unsafe_offset=0] = 0
    if n <= 0:
        return 0
    var digits = bi32(digits_addr)
    var limbs = bu32(limb_addr)
    for i in range(n):
        if digits[unsafe_offset=i] < 0 or digits[unsafe_offset=i] >= Int32(base):
            return -(2 + i)
    if max_limbs < 1:
        return -1
    limbs[unsafe_offset=0] = UInt32(0)
    var used = 1
    var K = chunk_width(base)
    var i = 0
    while i < n:
        var k = K
        if n - i < k:
            k = n - i
        var g = UInt64(0)
        for j in range(k):
            g = g * UInt64(base) + UInt64(digits[unsafe_offset=i + j])
        var m = bpow(base, k)
        var carry = g
        for j in range(used):
            var t = UInt64(limbs[unsafe_offset=j]) * m + carry
            limbs[unsafe_offset=j] = UInt32(t & UInt64(0xFFFFFFFF))
            carry = t >> UInt64(32)
        while carry != UInt64(0):
            if used >= max_limbs:
                return -1
            limbs[unsafe_offset=used] = UInt32(carry & UInt64(0xFFFFFFFF))
            carry = carry >> UInt64(32)
            used += 1
        i += k
    slots[unsafe_offset=0] = Int32(used)
    return 0


@export("bc_int_to_digits")
def bc_int_to_digits(limb_addr: Int, nlimb: Int, base: Int, out_addr: Int,
                     out_cap: Int) abi("C") -> Int:
    """Render the limb vector in radix `base`, most significant digit first.

    The digits are written into the tail of `out` and the index of the first one
    written is returned, so the caller reads `out[start:]`. A zero value writes
    nothing and returns `out_cap`. Returns -1 if `out_cap` is too small to hold
    the result even at full chunk granularity.
    """
    if base < 2 or nlimb <= 0:
        return 0 if nlimb <= 0 else -1
    var limbs = bu32(limb_addr)
    var out = bu8(out_addr)

    var top = nlimb - 1
    while top >= 0:
        if limbs[unsafe_offset=top] != UInt32(0):
            break
        top -= 1
    if top < 0:
        return out_cap

    var K = chunk_width(base)
    var M = bpow(base, K)
    var pos = out_cap
    var start = out_cap

    while top >= 0:
        var rem = UInt64(0)
        for j in range(top + 1):
            var i = top - j
            var cur = (rem << UInt64(32)) | UInt64(limbs[unsafe_offset=i])
            limbs[unsafe_offset=i] = UInt32(cur // M)
            rem = cur % M
        while top >= 0:
            if limbs[unsafe_offset=top] != UInt32(0):
                break
            top -= 1
        if pos < K:
            return -1
        # Every pass but the last is a full K digits wide, so its leading zero
        # digits are real. The last pass is narrower, and its padding is not.
        var ndig = 0
        var probe = rem
        while probe != UInt64(0):
            probe = probe // UInt64(base)
            ndig += 1
        pos -= K
        for j in range(K):
            var d = Int(rem % UInt64(base))
            rem = rem // UInt64(base)
            out[unsafe_offset=pos + (K - 1 - j)] = UInt8(d)
        if top < 0:
            start = pos + (K - ndig)

    return start


@export("bc_chunk_width")
def bc_chunk_width(base: Int) abi("C") -> Int:
    """Expose `chunk_width` so the Python layer can size its scratch exactly."""
    return chunk_width(base)
