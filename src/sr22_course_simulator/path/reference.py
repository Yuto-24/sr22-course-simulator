"""Wind-independent reference-path geometry."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Protocol, runtime_checkable

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.geometry import displace_position, enu_displacement
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation
from sr22_course_simulator.units import wrap_radians_2pi


@dataclass(frozen=True, slots=True)
class PathPoint:
    position: GeoPosition
    altitude_m: float
    label: str | None = None

    def __post_init__(self) -> None:
        """
        Validate that the path point altitude is finite.
        
        Raises:
            ValidationError: If the altitude is not finite.
        """
        if not math.isfinite(float(self.altitude_m)):
            raise ValidationError("path-point altitude must be finite")
        if self.label is not None and (
            not isinstance(self.label, str) or not self.label.strip()
        ):
            raise ValidationError("path-point label must not be empty when provided")


@runtime_checkable
class ReferencePath(Protocol):
    name: str

    def points(self) -> tuple[PathPoint, ...]:
        """
        Provide the generated immutable samples of the spiral path.
        
        Returns:
        	tuple[PathPoint, ...]: The path samples in traversal order.
        """


@dataclass(frozen=True, slots=True)
class PolylineReferencePath:
    name: str
    path_points: tuple[PathPoint, ...]
    evidence: EvidenceKind = EvidenceKind.ASSUMED
    citation: SourceCitation | None = None

    def __post_init__(self) -> None:
        """
        Normalize the path points and require at least two points.
        
        Raises:
            ValidationError: If fewer than two path points are provided.
        """
        object.__setattr__(self, "path_points", tuple(self.path_points))
        if len(self.path_points) < 2:
            raise ValidationError("a ReferencePath must contain at least two points")

    def points(self) -> tuple[PathPoint, ...]:
        """Return the immutable path samples."""
        return self.path_points


@dataclass(frozen=True, slots=True)
class PathProjection:
    radial_distance_m: float
    radial_error_m: float
    bearing_from_center_rad: float
    tangent_track_true_rad: float


@dataclass(frozen=True, slots=True)
class PylonSpiralPath:
    """Circular ground geometry with a linearly descending altitude profile.

    Positive sweep is clockwise/right when bearings are measured clockwise from
    True North.  Wind is intentionally absent from this object's API.
    """

    name: str
    center: GeoPosition
    radius_m: float
    start_bearing_rad: float
    sweep_rad: float
    start_altitude_m: float
    end_altitude_m: float
    point_count: int = 181
    evidence: EvidenceKind = EvidenceKind.ASSUMED
    citation: SourceCitation | None = None
    _points: tuple[PathPoint, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """
        Validate the spiral configuration and generate its immutable path points.
        
        Raises:
            ValidationError: If the path name, radius, bearings, sweep, altitudes, or
                point count is invalid.
        """
        if not self.name.strip():
            raise ValidationError("path name must not be empty")
        if not math.isfinite(float(self.radius_m)) or self.radius_m <= 0.0:
            raise ValidationError("radius_m must be finite and positive")
        for name in ("start_bearing_rad", "sweep_rad", "start_altitude_m", "end_altitude_m"):
            if not math.isfinite(float(getattr(self, name))):
                raise ValidationError(f"{name} must be finite")
        if self.sweep_rad == 0.0:
            raise ValidationError("sweep_rad must be non-zero")
        if isinstance(self.point_count, bool) or not isinstance(self.point_count, int) or self.point_count < 2:
            raise ValidationError("point_count must be at least 2")
        generated: list[PathPoint] = []
        for index in range(self.point_count):
            fraction = index / (self.point_count - 1)
            bearing = self.start_bearing_rad + self.sweep_rad * fraction
            position = displace_position(
                self.center,
                east_m=self.radius_m * math.sin(bearing),
                north_m=self.radius_m * math.cos(bearing),
            )
            altitude = self.start_altitude_m + (self.end_altitude_m - self.start_altitude_m) * fraction
            generated.append(PathPoint(position, altitude))
        object.__setattr__(self, "_points", tuple(generated))

    @property
    def turn_direction(self) -> int:
        """Return the spiral's turn direction.
        
        Returns:
        	int: `1` for a positive clockwise sweep, `-1` for a negative sweep.
        """
        return 1 if self.sweep_rad > 0.0 else -1

    def points(self) -> tuple[PathPoint, ...]:
        """Return the immutable path samples."""
        return self._points

    def project(self, position: GeoPosition) -> PathProjection:
        """
        Project a geographic position onto the path geometry.
        
        Parameters:
            position (GeoPosition): Geographic position to evaluate relative to the path center.
        
        Returns:
            PathProjection: Radial distance, radial error, center-relative bearing, and tangent true-track bearing.
        
        Raises:
            ValidationError: If the position coincides with the path center.
        """
        east, north = enu_displacement(self.center, position)
        distance = math.hypot(east, north)
        if distance == 0.0:
            raise ValidationError("pylon-center position has undefined path bearing")
        bearing = wrap_radians_2pi(math.atan2(east, north))
        tangent = wrap_radians_2pi(bearing + self.turn_direction * math.pi / 2)
        return PathProjection(
            radial_distance_m=distance,
            radial_error_m=distance - self.radius_m,
            bearing_from_center_rad=bearing,
            tangent_track_true_rad=tangent,
        )
