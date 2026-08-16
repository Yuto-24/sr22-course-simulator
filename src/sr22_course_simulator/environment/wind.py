"""Exchangeable wind providers using an East/North/Up vector convention."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.units import degrees_to_radians, knots_to_metres_per_second


@dataclass(frozen=True, slots=True)
class WindVector:
    east_mps: float
    north_mps: float
    up_mps: float = 0.0

    def __post_init__(self) -> None:
        """Validate that all wind components are finite numeric values.
        
        Raises:
            ValidationError: If any component is boolean or not finite.
        """
        if any(
            isinstance(value, bool) or not math.isfinite(float(value))
            for value in (self.east_mps, self.north_mps, self.up_mps)
        ):
            raise ValidationError("wind components must be finite")

    @property
    def horizontal_speed_mps(self) -> float:
        """Calculate the horizontal wind speed from the eastward and northward components.
        
        Returns:
        	float: The horizontal wind speed in metres per second.
        """
        return math.hypot(self.east_mps, self.north_mps)


@runtime_checkable
class WindProvider(Protocol):
    def velocity_at(
        self,
        position: GeoPosition,
        altitude_m: float,
        time_s: float,
    ) -> WindVector:
        """
        Provide the wind velocity at a position, altitude, and time.
        
        Parameters:
            altitude_m (float): Altitude in metres.
            time_s (float): Time in seconds.
        
        Returns:
            WindVector: Wind velocity components toward the East, North, and Up directions.
        """


@dataclass(frozen=True, slots=True)
class NoWind:
    def velocity_at(
        self,
        position: GeoPosition,
        altitude_m: float,
        time_s: float,
    ) -> WindVector:
        """
        Provide zero wind at any position, altitude, or time.
        
        Returns:
            WindVector: A zero-velocity wind vector.
        """
        return WindVector(0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class ConstantWind:
    vector: WindVector

    @classmethod
    def from_meteorological(
        cls,
        *,
        from_direction_deg_true: float,
        speed_mps: float,
        vertical_mps: float = 0.0,
    ) -> "ConstantWind":
        """
        Construct constant wind from a meteorological direction and speed.
        
        Parameters:
            from_direction_deg_true (float): Direction the wind comes from, measured clockwise from true north in degrees.
            speed_mps (float): Horizontal wind speed in meters per second.
            vertical_mps (float): Upward wind speed in meters per second.
        
        Returns:
            ConstantWind: A constant wind provider with the specified velocity.
        """

        speed = float(speed_mps)
        direction = float(from_direction_deg_true)
        if not math.isfinite(speed) or speed < 0.0:
            raise ValidationError("wind speed must be finite and non-negative")
        if not math.isfinite(direction):
            raise ValidationError("wind direction must be finite")
        angle = degrees_to_radians(direction)
        return cls(
            WindVector(
                east_mps=-speed * math.sin(angle),
                north_mps=-speed * math.cos(angle),
                up_mps=float(vertical_mps),
            )
        )

    @classmethod
    def from_meteorological_knots(
        cls,
        *,
        from_direction_deg_true: float,
        speed_kt: float,
    ) -> "ConstantWind":
        """
        Create a constant wind from a meteorological direction and speed in knots.
        
        Parameters:
            from_direction_deg_true (float): Direction the wind comes from, in true degrees.
            speed_kt (float): Wind speed in knots.
        
        Returns:
            ConstantWind: A constant wind with zero vertical velocity.
        """
        return cls.from_meteorological(
            from_direction_deg_true=from_direction_deg_true,
            speed_mps=knots_to_metres_per_second(speed_kt),
        )

    def velocity_at(
        self,
        position: GeoPosition,
        altitude_m: float,
        time_s: float,
    ) -> WindVector:
        """
        Provide the configured wind vector at any position, altitude, and time.
        
        Returns:
        	WindVector: The constant wind vector.
        """
        return self.vector
