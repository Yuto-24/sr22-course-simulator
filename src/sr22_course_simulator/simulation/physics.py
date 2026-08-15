"""Analytical relationships used by the quasi-steady integrator."""

from __future__ import annotations

from dataclasses import dataclass
import math

from sr22_course_simulator.environment.wind import WindVector
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.units import wrap_radians_2pi

STANDARD_GRAVITY_MPS2 = 9.80665


def coordinated_turn_rate_rad_s(
    true_airspeed_mps: float,
    bank_rad: float,
    *,
    gravity_mps2: float = STANDARD_GRAVITY_MPS2,
) -> float:
    """
    Calculate the ideal heading rate for a coordinated turn.
    
    Parameters:
        gravity_mps2 (float): Gravitational acceleration used in the calculation.
    
    Returns:
        float: The signed heading rate in radians per second.
    
    Raises:
        ValidationError: If the true airspeed is not finite and positive or the bank
            angle is not finite or lies outside the open interval (-π/2, π/2).
    """

    speed = float(true_airspeed_mps)
    bank = float(bank_rad)
    if not math.isfinite(speed) or speed <= 0.0:
        raise ValidationError("true_airspeed_mps must be finite and positive")
    if not math.isfinite(bank) or not -math.pi / 2 < bank < math.pi / 2:
        raise ValidationError("bank_rad must lie strictly between -pi/2 and pi/2")
    return float(gravity_mps2) * math.tan(bank) / speed


def coordinated_turn_radius_m(
    true_airspeed_mps: float,
    bank_rad: float,
    *,
    gravity_mps2: float = STANDARD_GRAVITY_MPS2,
) -> float:
    """
    Calculate the signed radius of an ideal coordinated turn.
    
    Parameters:
    	true_airspeed_mps (float): True airspeed in meters per second.
    	bank_rad (float): Bank angle in radians.
    	gravity_mps2 (float): Gravitational acceleration in meters per second squared.
    
    Returns:
    	float: Signed turn radius in meters, or infinity for a zero bank angle.
    """

    rate = coordinated_turn_rate_rad_s(true_airspeed_mps, bank_rad, gravity_mps2=gravity_mps2)
    return math.inf if rate == 0.0 else float(true_airspeed_mps) / rate


def coordinated_load_factor(bank_rad: float) -> float:
    """
    Calculate the load factor for a coordinated turn at a given bank angle.
    
    Parameters:
    	bank_rad (float): Bank angle in radians.
    
    Returns:
    	float: The coordinated-turn load factor.
    """
    bank = float(bank_rad)
    if not math.isfinite(bank) or not -math.pi / 2 < bank < math.pi / 2:
        raise ValidationError("bank_rad must lie strictly between -pi/2 and pi/2")
    return 1.0 / math.cos(bank)


@dataclass(frozen=True, slots=True)
class VelocityENU:
    east_mps: float
    north_mps: float
    up_mps: float

    @property
    def horizontal_speed_mps(self) -> float:
        """Compute the horizontal speed from the east and north velocity components.
        
        Returns:
        	float: The horizontal speed in meters per second.
        """
        return math.hypot(self.east_mps, self.north_mps)

    @property
    def track_true_rad_or_none(self) -> float | None:
        """
        Determine the true track from the horizontal velocity components.
        
        Returns:
        	float | None: The true track in radians wrapped to [0, 2π), or `None` when horizontal velocity is zero.
        """

        if self.horizontal_speed_mps == 0.0:
            return None
        return wrap_radians_2pi(math.atan2(self.east_mps, self.north_mps))

    @property
    def track_true_rad(self) -> float:
        """Return the true track angle.
        
        Raises:
            ValidationError: If the horizontal velocity is zero.
        
        Returns:
            float: The wrapped true track angle in radians.
        """

        track = self.track_true_rad_or_none
        if track is None:
            raise ValidationError("track is undefined for zero horizontal velocity")
        return track


def air_velocity_enu(
    *,
    true_airspeed_mps: float,
    heading_true_rad: float,
    flight_path_angle_rad: float,
) -> VelocityENU:
    """
    Convert true airspeed, heading, and flight-path angle into an ENU air-velocity vector.
    
    Parameters:
    	true_airspeed_mps (float): Positive true airspeed in meters per second.
    	heading_true_rad (float): True heading in radians.
    	flight_path_angle_rad (float): Flight-path angle in radians, strictly between -π/2 and π/2.
    
    Returns:
    	VelocityENU: The corresponding east, north, and up air-velocity components.
    """
    speed = float(true_airspeed_mps)
    gamma = float(flight_path_angle_rad)
    if not math.isfinite(speed) or speed <= 0.0:
        raise ValidationError("true_airspeed_mps must be finite and positive")
    if not math.isfinite(gamma) or not -math.pi / 2 < gamma < math.pi / 2:
        raise ValidationError("flight_path_angle_rad must lie strictly between -pi/2 and pi/2")
    horizontal = speed * math.cos(gamma)
    return VelocityENU(
        east_mps=horizontal * math.sin(heading_true_rad),
        north_mps=horizontal * math.cos(heading_true_rad),
        up_mps=speed * math.sin(gamma),
    )


def add_wind(air_velocity: VelocityENU, wind: WindVector) -> VelocityENU:
    """Combine an air-velocity vector with a wind vector.
    
    Parameters:
    	air_velocity (VelocityENU): Air velocity in east, north, and up components.
    	wind (WindVector): Wind velocity components to add.
    
    Returns:
    	VelocityENU: Resulting ground-velocity vector.
    """
    return VelocityENU(
        east_mps=air_velocity.east_mps + wind.east_mps,
        north_mps=air_velocity.north_mps + wind.north_mps,
        up_mps=air_velocity.up_mps + wind.up_mps,
    )
