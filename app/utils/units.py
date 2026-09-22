"""Unit conversion utilities for the PlanForge pipeline.

Provides stateless conversion of area and dimension strings into SI units
(square metres and metres respectively).  No external dependencies — stdlib
``re`` only.

Supported area units
--------------------
- sqm / m² / m^2 / square metres (passthrough)
- sqft / sq ft / ft² / square feet
- sqyd / sq yd / sq yard / square yards
- marla  (Pakistani/South-Asian land measure; 1 marla = 20.903 sqm)
- kanal  (1 kanal = 20 marla = 418.06 sqm)
- acre   (1 acre = 4046.86 sqm)
- hectare / ha (1 ha = 10 000 sqm)

Supported dimension units
--------------------------
- m / meters / metre  (passthrough)
- ft / feet / foot / ' (apostrophe)
- in / inches / ''
- cm  (1 cm = 0.01 m)

Functions return ``None`` when no recognisable numeric value can be extracted.
"""

from __future__ import annotations
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_SQM_PER_SQFT = 0.09290304
_SQM_PER_SQYD = 0.83612736
_SQM_PER_MARLA = 20.9032
_SQM_PER_KANAL = 418.064
_SQM_PER_ACRE = 4046.8564
_SQM_PER_HECTARE = 10_000.0

_M_PER_FT = 0.3048
_M_PER_INCH = 0.0254
_M_PER_CM = 0.01

# ---------------------------------------------------------------------------
# Area parsing
# ---------------------------------------------------------------------------

# Each entry: (compiled pattern, conversion factor to sqm)
_AREA_PATTERNS: list[tuple[re.Pattern, float]] = [
    # Square feet — must come before bare 'ft' patterns
    (re.compile(r"([\d]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft[²2]|square\s*f(?:oo|ee)t)", re.I), _SQM_PER_SQFT),
    # Square yards
    (re.compile(r"([\d]+(?:\.\d+)?)\s*(?:sq\.?\s*yd|sqyd|yd[²2]|square\s*yards?)", re.I), _SQM_PER_SQYD),
    # Marla
    (re.compile(r"([\d]+(?:\.\d+)?)\s*marlas?", re.I), _SQM_PER_MARLA),
    # Kanal
    (re.compile(r"([\d]+(?:\.\d+)?)\s*kanals?", re.I), _SQM_PER_KANAL),
    # Acre
    (re.compile(r"([\d]+(?:\.\d+)?)\s*acres?", re.I), _SQM_PER_ACRE),
    # Hectare
    (re.compile(r"([\d]+(?:\.\d+)?)\s*(?:hectares?|ha)\b", re.I), _SQM_PER_HECTARE),
    # Square metres (passthrough — must be last to avoid shadowing the above)
    (re.compile(r"([\d]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m[²2]|square\s*met(?:re|er)s?)", re.I), 1.0),
]


def parse_area_sqm(text: str) -> Optional[float]:
    """Extract and convert an area value from *text* into square metres.

    The first recognisable pattern in *text* is returned.  Returns ``None`` if
    no area value is found.

    Args:
        text: Arbitrary string that may contain an area mention.

    Returns:
        Area in square metres, or ``None``.

    Examples::

        >>> parse_area_sqm("plot area 200 sqm")
        200.0
        >>> parse_area_sqm("2000 sqft")
        185.806...
        >>> parse_area_sqm("5 marla")
        104.516
    """
    for pattern, factor in _AREA_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                return float(m.group(1)) * factor
            except (ValueError, IndexError):
                continue
    return None


# ---------------------------------------------------------------------------
# Dimension (length) parsing
# ---------------------------------------------------------------------------

_DIM_PATTERNS: list[tuple[re.Pattern, float]] = [
    # Feet + inches combined: 10'6" or 10 ft 6 in
    (re.compile(r"([\d]+)\s*(?:ft|'|feet|foot)\s*([\d]+)\s*(?:in|\"|\u2019\u2019|inches?)", re.I), None),
    # Feet only: 15ft, 15 feet, 15', 15 ft
    (re.compile(r"([\d]+(?:\.\d+)?)\s*(?:(?:ft|feet|foot)\b|'|\u2019)", re.I), _M_PER_FT),
    # Inches only: 6 in, 6"
    (re.compile(r"([\d]+(?:\.\d+)?)\s*(?:(?:in|inches?)\b|\"|\u201d|\u2019\u2019)", re.I), _M_PER_INCH),
    # Centimetres: 300cm, 300 cm
    (re.compile(r"([\d]+(?:\.\d+)?)\s*cm\b", re.I), _M_PER_CM),
    # Metres (passthrough): 15m, 15 m, 15 metres, 15 meters
    (re.compile(r"([\d]+(?:\.\d+)?)\s*(?:m|metres?|meters?)\b", re.I), 1.0),
]


def parse_dimension_m(text: str) -> Optional[float]:
    """Extract and convert a single linear dimension from *text* into metres.

    Handles compound feet+inches (e.g. ``10'6"``).  Returns the first match
    found, or ``None`` if no recognisable value is present.

    Args:
        text: Arbitrary string that may contain a dimension mention.

    Returns:
        Dimension in metres, or ``None``.

    Examples::

        >>> parse_dimension_m("15 m")
        15.0
        >>> parse_dimension_m("50 ft")
        15.24
        >>> parse_dimension_m("10'6\\"")
        3.2004
    """
    # Special case: combined feet + inches
    ft_in_pat = _DIM_PATTERNS[0][0]
    m = ft_in_pat.search(text)
    if m:
        try:
            feet = float(m.group(1))
            inches = float(m.group(2))
            return feet * _M_PER_FT + inches * _M_PER_INCH
        except (ValueError, IndexError):
            pass

    # Remaining patterns
    for pattern, factor in _DIM_PATTERNS[1:]:
        m = pattern.search(text)
        if m:
            try:
                return float(m.group(1)) * factor
            except (ValueError, IndexError):
                continue
    return None
