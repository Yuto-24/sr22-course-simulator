"""Reference-path objects, always separate from simulated trajectories."""

from sr22_course_simulator.path.reference import (
    PathPoint,
    PathProjection,
    PolylineReferencePath,
    PylonSpiralPath,
    ReferencePath,
)
from sr22_course_simulator.path.short_downwind import (
    ShortDownwindCircleSpec,
    generate_short_downwind_circle,
)
from sr22_course_simulator.path.traffic_pattern import (
    CoordinatedTurnProfile,
    PatternLabel,
    PatternSide,
    TrafficPatternSpec,
    TurnProfileSample,
    aiming_marker_distance_m,
    aiming_marker_elevation_ft,
    generate_coordinated_turn_profile,
    generate_traffic_pattern,
)

__all__ = [
    "PathPoint",
    "PathProjection",
    "PolylineReferencePath",
    "PylonSpiralPath",
    "ReferencePath",
    "ShortDownwindCircleSpec",
    "CoordinatedTurnProfile",
    "PatternLabel",
    "PatternSide",
    "TrafficPatternSpec",
    "TurnProfileSample",
    "aiming_marker_distance_m",
    "aiming_marker_elevation_ft",
    "generate_coordinated_turn_profile",
    "generate_short_downwind_circle",
    "generate_traffic_pattern",
]
