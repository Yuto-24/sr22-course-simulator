"""Forward integration, analytical physics, termination and trajectories."""

from sr22_course_simulator.simulation.integrator import (
    ConstantFlightInput,
    FlightInputSource,
    ForwardSimulator,
    SimulationConfig,
    SimulationProgress,
    simulate_forward,
)
from sr22_course_simulator.simulation.physics import (
    STANDARD_GRAVITY_MPS2,
    coordinated_load_factor,
    coordinated_turn_radius_m,
    coordinated_turn_rate_rad_s,
)
from sr22_course_simulator.simulation.termination import (
    AccumulatedTurn,
    AltitudeAglAtOrBelow,
    AltitudeAtOrBelow,
    AnyOf,
    ElapsedTime,
    HeadingWithin,
    TerminationEvent,
    TerminationRole,
)
from sr22_course_simulator.simulation.trajectory import SimulationOutcome, SimulationResult, Trajectory

__all__ = [
    "AccumulatedTurn",
    "AltitudeAglAtOrBelow",
    "AltitudeAtOrBelow",
    "AnyOf",
    "ConstantFlightInput",
    "ElapsedTime",
    "FlightInputSource",
    "ForwardSimulator",
    "HeadingWithin",
    "STANDARD_GRAVITY_MPS2",
    "SimulationConfig",
    "SimulationOutcome",
    "SimulationProgress",
    "SimulationResult",
    "TerminationEvent",
    "TerminationRole",
    "Trajectory",
    "coordinated_load_factor",
    "coordinated_turn_radius_m",
    "coordinated_turn_rate_rad_s",
    "simulate_forward",
]
