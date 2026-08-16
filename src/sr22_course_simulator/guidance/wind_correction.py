"""Analytical wind-triangle calculations shared by path guidance."""

from __future__ import annotations

from dataclasses import dataclass
import math

from sr22_course_simulator.environment.wind import WindVector
from sr22_course_simulator.errors import UnsupportedModelError, ValidationError
from sr22_course_simulator.units import wrap_radians_2pi


@dataclass(frozen=True, slots=True)
class WindCorrectionSolution:
    desired_track_true_rad: float
    required_heading_true_rad: float
    ground_speed_mps: float
    crosswind_mps: float


def solve_heading_for_ground_track(
    *,
    desired_track_true_rad: float,
    true_airspeed_mps: float,
    wind: WindVector,
) -> WindCorrectionSolution:
    """
    Determine the heading and ground speed required to maintain a desired ground track.
    
    Parameters:
        desired_track_true_rad (float): Desired true ground track in radians.
        true_airspeed_mps (float): True airspeed in meters per second.
        wind (WindVector): Wind velocity toward the east and north in meters per second.
    
    Returns:
        WindCorrectionSolution: The wrapped desired track, required true heading,
            ground speed, and right-side crosswind component.
    
    Raises:
        ValidationError: If the track or airspeed is not finite, or the airspeed is
            not positive.
        UnsupportedModelError: If the crosswind exceeds true airspeed or the
            headwind prevents positive progress along the desired track.
    """

    track = float(desired_track_true_rad)
    speed = float(true_airspeed_mps)
    if not math.isfinite(track) or not math.isfinite(speed) or speed <= 0.0:
        raise ValidationError("desired track must be finite and TAS must be positive")
    along_east = math.sin(track)
    along_north = math.cos(track)
    right_east = math.cos(track)
    right_north = -math.sin(track)
    wind_along = wind.east_mps * along_east + wind.north_mps * along_north
    wind_cross = wind.east_mps * right_east + wind.north_mps * right_north
    if abs(wind_cross) > speed:
        raise UnsupportedModelError("crosswind exceeds TAS; desired ground track is infeasible")
    air_along = math.sqrt(max(0.0, speed * speed - wind_cross * wind_cross))
    ground_speed = air_along + wind_along
    if ground_speed <= 0.0:
        raise UnsupportedModelError("headwind prevents positive progress on desired ground track")
    air_cross = -wind_cross
    air_east = air_along * along_east + air_cross * right_east
    air_north = air_along * along_north + air_cross * right_north
    heading = wrap_radians_2pi(math.atan2(air_east, air_north))
    return WindCorrectionSolution(
        desired_track_true_rad=wrap_radians_2pi(track),
        required_heading_true_rad=heading,
        ground_speed_mps=ground_speed,
        crosswind_mps=wind_cross,
    )
