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
    """Convert a distance from feet to metres.
    
    Parameters:
    	value_ft (float): Distance in feet.
    
    Returns:
    	float: Equivalent distance in metres.
    """
    return float(value_ft) * FT_TO_M


def metres_to_feet(value_m: float) -> float:
    """Convert a distance in metres to feet.
    
    Parameters:
        value_m (float): Distance in metres.
    
    Returns:
        float: The equivalent distance in feet.
    """
    return float(value_m) / FT_TO_M


def knots_to_metres_per_second(value_kt: float) -> float:
    """Convert a speed from knots to metres per second.
    
    Parameters:
    	value_kt (float): Speed in knots.
    
    Returns:
    	float: The equivalent speed in metres per second.
    """
    return float(value_kt) * KT_TO_MPS


def metres_per_second_to_knots(value_mps: float) -> float:
    """Convert a speed from metres per second to knots.
    
    Parameters:
        value_mps (float): Speed in metres per second.
    
    Returns:
        float: The equivalent speed in knots.
    """
    return float(value_mps) / KT_TO_MPS


def nautical_miles_to_metres(value_nm: float) -> float:
    """
    Convert a distance from nautical miles to metres.
    
    Parameters:
        value_nm (float): Distance in nautical miles.
    
    Returns:
        float: Equivalent distance in metres.
    """
    return float(value_nm) * NM_TO_M


def metres_to_nautical_miles(value_m: float) -> float:
    """Convert a distance in metres to nautical miles.
    
    Parameters:
    	value_m (float): Distance in metres.
    
    Returns:
    	float: The equivalent distance in nautical miles.
    """
    return float(value_m) / NM_TO_M


def feet_per_minute_to_metres_per_second(value_fpm: float) -> float:
    """Convert a rate in feet per minute to metres per second.
    
    Parameters:
    	value_fpm (float): Rate in feet per minute.
    
    Returns:
    	float: The equivalent rate in metres per second.
    """
    return feet_to_metres(value_fpm) / MIN_TO_S


def metres_per_second_to_feet_per_minute(value_mps: float) -> float:
    """Convert a speed from metres per second to feet per minute.
    
    Parameters:
    	value_mps (float): Speed in metres per second.
    
    Returns:
    	float: Equivalent speed in feet per minute.
    """
    return metres_to_feet(value_mps) * MIN_TO_S


def pounds_to_kilograms(value_lb: float) -> float:
    """Convert a mass from pounds to kilograms.
    
    Parameters:
    	value_lb (float): Mass in pounds.
    
    Returns:
    	float: The equivalent mass in kilograms.
    """
    return float(value_lb) * LB_TO_KG


def kilograms_to_pounds(value_kg: float) -> float:
    """Convert a mass from kilograms to pounds.
    
    Parameters:
    	value_kg (float): Mass in kilograms.
    
    Returns:
    	float: The equivalent mass in pounds.
    """
    return float(value_kg) / LB_TO_KG


def degrees_to_radians(value_deg: float) -> float:
    """
    Convert an angle from degrees to radians.
    
    Parameters:
    	value_deg (float): Angle in degrees.
    
    Returns:
    	float: The equivalent angle in radians.
    """
    return math.radians(float(value_deg))


def radians_to_degrees(value_rad: float) -> float:
    """Convert an angle from radians to degrees.
    
    Parameters:
    	value_rad (float): Angle expressed in radians.
    
    Returns:
    	float: The equivalent angle in degrees.
    """
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
