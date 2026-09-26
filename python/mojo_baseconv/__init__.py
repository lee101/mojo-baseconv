"""mojo-baseconv: generic base conversion with the radix transform in Mojo.

The upstream `baseconv` 0.1a distribution is no longer downloadable, so this
package is built against the API its PyPI long description documents and tested
against analytic truth rather than against the real package. See the README for
exactly what that means.
"""

from .core import (
    ALPHA,
    ALPHA_LOWER,
    ALPHA_UPPER,
    BINARY,
    DECIMAL,
    HEXADECIMAL,
    OCTAL,
    Base,
    Number,
)

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
__version__ = "0.1.0"
