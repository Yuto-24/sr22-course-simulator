"""Small-area geographic helpers using an explicit spherical-Earth assumption."""

from __future__ import annotations

import math

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.errors import UnsupportedModelError, ValidationError

# IUGG mean Earth radius.  The local tangent approximation is explicitly limited
# to training-course-scale paths; it is not a geodetic/navigation database model.
MEAN_EARTH_RADIUS_M = 6_371_008.8


def _wrap_longitude_deg(longitude_deg: float) -> float:
    """
    Normalize a longitude to the range from -180 to 180 degrees, preserving positive 180 degrees.
    
    Parameters:
    	longitude_deg (float): Longitude in degrees.
    
    Returns:
    	float: The normalized longitude in degrees.
    """
    wrapped = (longitude_deg + 180.0) % 360.0 - 180.0
    return 180.0 if wrapped == -180.0 and longitude_deg > 0.0 else wrapped


def displace_position(
    origin: GeoPosition,
    *,
    east_m: float,
    north_m: float,
) -> GeoPosition:
    """
    Apply a local east and north displacement to a geographic position.
    
    Parameters:
        origin (GeoPosition): Position from which to apply the displacement.
        east_m (float): Eastward displacement in meters.
        north_m (float): Northward displacement in meters.
    
    Returns:
        GeoPosition: The displaced position with its longitude normalized to the
        range [-180°, 180°].
    
    Raises:
        ValidationError: If either displacement is not finite.
        UnsupportedModelError: If the displacement operation reaches a pole.
    """

    east = float(east_m)
    north = float(north_m)
    if not math.isfinite(east) or not math.isfinite(north):
        raise ValidationError("ENU displacement must be finite")
    lat0 = math.radians(origin.latitude_deg)
    lat1 = lat0 + north / MEAN_EARTH_RADIUS_M
    mean_lat = 0.5 * (lat0 + lat1)
    cosine = math.cos(mean_lat)
    if abs(cosine) < 1e-12:
        raise UnsupportedModelError("local tangent displacement is unsupported at the poles")
    lon1 = math.radians(origin.longitude_deg) + east / (MEAN_EARTH_RADIUS_M * cosine)
    return GeoPosition(math.degrees(lat1), _wrap_longitude_deg(math.degrees(lon1)))


def enu_displacement(origin: GeoPosition, target: GeoPosition) -> tuple[float, float]:
    """
    Compute the local eastward and northward displacement between two positions.
    
    Returns:
        tuple[float, float]: The eastward and northward displacements in meters.
    """

    lat0 = math.radians(origin.latitude_deg)
    lat1 = math.radians(target.latitude_deg)
    dlat = lat1 - lat0
    dlon = (math.radians(target.longitude_deg - origin.longitude_deg) + math.pi) % math.tau - math.pi
    mean_lat = 0.5 * (lat0 + lat1)
    east = dlon * MEAN_EARTH_RADIUS_M * math.cos(mean_lat)
    north = dlat * MEAN_EARTH_RADIUS_M
    return east, north


def distance_m(origin: GeoPosition, target: GeoPosition) -> float:
    """Calculate the planar distance between two geographic positions.
    
    Parameters:
        origin (GeoPosition): Starting geographic position.
        target (GeoPosition): Destination geographic position.
    
    Returns:
        float: Approximate distance between the positions in meters.
    """
    east, north = enu_displacement(origin, target)
    return math.hypot(east, north)
