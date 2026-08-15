"""Explicit aviation/SI conversion boundaries.

All numerical simulation internals use SI units.  These helpers deliberately do
not include a fuel-volume-to-mass conversion: that conversion requires a sourced
fuel-density convention and belongs in loading/ingestion configuration.
"""

from __future__ import annotations

import math

FT_TO_M = 0.3048
KT_TO_MPS = 1852.0 / 3600.0
NM_TO_M = 1852.0
LB_TO_KG = 0.45359237
MIN_TO_S = 60.0


def feet_to_metres(value_ft: float) -> float:
    return float(value_ft) * FT_TO_M


def metres_to_feet(value_m: float) -> float:
    return float(value_m) / FT_TO_M


def knots_to_metres_per_second(value_kt: float) -> float:
    return float(value_kt) * KT_TO_MPS


def metres_per_second_to_knots(value_mps: float) -> float:
    return float(value_mps) / KT_TO_MPS


def nautical_miles_to_metres(value_nm: float) -> float:
    return float(value_nm) * NM_TO_M


def metres_to_nautical_miles(value_m: float) -> float:
    return float(value_m) / NM_TO_M


def feet_per_minute_to_metres_per_second(value_fpm: float) -> float:
    return feet_to_metres(value_fpm) / MIN_TO_S


def metres_per_second_to_feet_per_minute(value_mps: float) -> float:
    return metres_to_feet(value_mps) * MIN_TO_S


def pounds_to_kilograms(value_lb: float) -> float:
    return float(value_lb) * LB_TO_KG


def kilograms_to_pounds(value_kg: float) -> float:
    return float(value_kg) / LB_TO_KG


def degrees_to_radians(value_deg: float) -> float:
    return math.radians(float(value_deg))


def radians_to_degrees(value_rad: float) -> float:
    return math.degrees(float(value_rad))


def wrap_radians_2pi(value_rad: float) -> float:
    """Wrap an angle into ``[0, 2*pi)``."""

    wrapped = float(value_rad) % math.tau
    return 0.0 if wrapped >= math.tau else wrapped


def wrap_degrees_360(value_deg: float) -> float:
    """Wrap an angle into ``[0, 360)``."""

    wrapped = float(value_deg) % 360.0
    return 0.0 if wrapped >= 360.0 else wrapped


def signed_angle_difference_rad(target_rad: float, current_rad: float) -> float:
    """Shortest signed rotation from ``current`` to ``target`` in ``[-pi, pi)``."""

    return (float(target_rad) - float(current_rad) + math.pi) % math.tau - math.pi
