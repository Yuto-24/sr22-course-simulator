"""Atmosphere, terrain and wind grouped as external environment state."""

from __future__ import annotations

from dataclasses import dataclass, field

from sr22_course_simulator.environment.atmosphere import Atmosphere, FlatTerrain, TerrainProvider
from sr22_course_simulator.environment.wind import ConstantWind, NoWind, WindProvider, WindVector


@dataclass(frozen=True, slots=True)
class Environment:
    atmosphere: Atmosphere
    wind: WindProvider = field(default_factory=NoWind)
    terrain: TerrainProvider = field(default_factory=FlatTerrain)

    def __post_init__(self) -> None:
        if not isinstance(self.atmosphere, Atmosphere):
            raise TypeError("atmosphere must be an Atmosphere")
        if not isinstance(self.wind, WindProvider):
            raise TypeError("wind must implement WindProvider")
        if not isinstance(self.terrain, TerrainProvider):
            raise TypeError("terrain must implement TerrainProvider")


__all__ = [
    "Atmosphere",
    "ConstantWind",
    "Environment",
    "FlatTerrain",
    "NoWind",
    "TerrainProvider",
    "WindProvider",
    "WindVector",
]
