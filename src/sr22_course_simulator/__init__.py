"""SR22 course simulator public package.

No source-backed SR22 descent performance data is bundled yet.  The core API
therefore distinguishes source tables, analytical physics, explicit assumptions
and unsupported regions.
"""

from sr22_course_simulator.aircraft import (
    AircraftState,
    FlapSetting,
    FlightInput,
    GeoPosition,
    InitialState,
    Loading,
)
from sr22_course_simulator.environment import Environment
from sr22_course_simulator.simulation import SimulationResult, Trajectory, simulate_forward

__version__ = "0.1.0"

__all__ = [
    "AircraftState",
    "Environment",
    "FlapSetting",
    "FlightInput",
    "GeoPosition",
    "InitialState",
    "Loading",
    "SimulationResult",
    "Trajectory",
    "simulate_forward",
]
