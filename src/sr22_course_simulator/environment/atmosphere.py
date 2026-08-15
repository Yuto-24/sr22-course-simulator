"""Minimal atmosphere and terrain interfaces used by current performance queries."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.errors import ValidationError


@dataclass(frozen=True, slots=True)
class Atmosphere:
    temperature_k: float
    pressure_altitude_m: float
    static_pressure_pa: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.temperature_k)) or self.temperature_k <= 0.0:
            raise ValidationError("temperature_k must be finite and positive")
        if not math.isfinite(float(self.pressure_altitude_m)):
            raise ValidationError("pressure_altitude_m must be finite")
        if self.static_pressure_pa is not None and (
            not math.isfinite(float(self.static_pressure_pa)) or self.static_pressure_pa <= 0.0
        ):
            raise ValidationError("static_pressure_pa must be finite and positive when supplied")


@runtime_checkable
class TerrainProvider(Protocol):
    def elevation_msl_m(self, position: GeoPosition) -> float:
        """Return ground elevation above mean sea level."""


@dataclass(frozen=True, slots=True)
class FlatTerrain:
    elevation_m: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.elevation_m)):
            raise ValidationError("terrain elevation must be finite")

    def elevation_msl_m(self, position: GeoPosition) -> float:
        return self.elevation_m
