"""Procedure/path-driven guidance, separate from direct-input simulation."""

from sr22_course_simulator.guidance.spiral_descent import (
    GuidanceRecord,
    GuidedSimulationResult,
    SpiralDescentGuidance,
    SpiralGuidanceConfig,
    simulate_guided_spiral_descent,
)
from sr22_course_simulator.guidance.wind_correction import (
    WindCorrectionSolution,
    solve_heading_for_ground_track,
)

__all__ = [
    "GuidanceRecord",
    "GuidedSimulationResult",
    "SpiralDescentGuidance",
    "SpiralGuidanceConfig",
    "WindCorrectionSolution",
    "simulate_guided_spiral_descent",
    "solve_heading_for_ground_track",
]
