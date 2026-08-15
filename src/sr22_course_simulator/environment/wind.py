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
        if any(
            isinstance(value, bool) or not math.isfinite(float(value))
            for value in (self.east_mps, self.north_mps, self.up_mps)
        ):
            raise ValidationError("wind components must be finite")

    @property
    def horizontal_speed_mps(self) -> float:
        return math.hypot(self.east_mps, self.north_mps)


@runtime_checkable
class WindProvider(Protocol):
    def velocity_at(
        self,
        position: GeoPosition,
        altitude_m: float,
        time_s: float,
    ) -> WindVector:
        """Return the wind velocity toward East/North/Up at a state point."""


@dataclass(frozen=True, slots=True)
class NoWind:
    def velocity_at(
        self,
        position: GeoPosition,
        altitude_m: float,
        time_s: float,
    ) -> WindVector:
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
        """Construct constant wind from meteorological FROM direction."""

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
        return self.vector
