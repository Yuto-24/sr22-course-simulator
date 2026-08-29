"""Task-defined Short Downwind and steady coordinated-circle paths."""

from __future__ import annotations

from dataclasses import dataclass
import math

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.airport import RunwaySpec
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.geometry import displace_position, enu_displacement
from sr22_course_simulator.path.reference import (
    PathPoint,
    PolylineReferencePath,
    PylonSpiralPath,
)
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation
from sr22_course_simulator.simulation.physics import coordinated_turn_radius_m
from sr22_course_simulator.units import knots_to_metres_per_second


@dataclass(frozen=True, slots=True)
class ShortDownwindCircleSpec:
    """Configuration for a constant-altitude circle tangent to Short Downwind."""

    name: str
    runway: RunwaySpec
    tangency_position: GeoPosition
    altitude_m: float
    source: SourceCitation
    true_airspeed_kt: float = 110.0
    bank_deg: float = 22.0
    point_count: int = 145

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("Short Downwind circle name must not be empty")
        if not isinstance(self.runway, RunwaySpec):
            raise ValidationError("Short Downwind circle runway must be RunwaySpec")
        if not isinstance(self.tangency_position, GeoPosition):
            raise ValidationError("Short Downwind circle tangency must be GeoPosition")
        if not isinstance(self.source, SourceCitation):
            raise ValidationError("Short Downwind circle source must be SourceCitation")
        for field_name in ("altitude_m", "true_airspeed_kt", "bank_deg"):
            value = getattr(self, field_name)
            if isinstance(value, bool):
                raise ValidationError(f"{field_name} must be finite")
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"{field_name} must be finite") from exc
            if not math.isfinite(numeric):
                raise ValidationError(f"{field_name} must be finite")
            object.__setattr__(self, field_name, numeric)
        if self.true_airspeed_kt <= 0.0:
            raise ValidationError("true_airspeed_kt must be positive")
        if not 0.0 < self.bank_deg < 90.0:
            raise ValidationError("bank_deg must be between zero and 90 degrees")
        if (
            isinstance(self.point_count, bool)
            or not isinstance(self.point_count, int)
            or self.point_count < 3
        ):
            raise ValidationError("point_count must be an integer of at least three")

    @property
    def radius_m(self) -> float:
        """Return the physics-derived steady coordinated-turn radius."""

        return abs(
            coordinated_turn_radius_m(
                knots_to_metres_per_second(self.true_airspeed_kt),
                math.radians(self.bank_deg),
            )
        )


def generate_short_downwind_circle(
    spec: ShortDownwindCircleSpec,
) -> PolylineReferencePath:
    """Generate a clockwise circle tangent to the RWY09 Short Downwind axis.

    The task-provided tangency point remains fixed.  The center is moved along
    the runway's left normal by the physics-derived radius, so replacing the
    original circle radius does not detach it from the Short Downwind axis.
    """

    normal_east, normal_north = spec.runway.left_normal_unit_vector
    center = displace_position(
        spec.tangency_position,
        east_m=normal_east * spec.radius_m,
        north_m=normal_north * spec.radius_m,
    )
    tangent_east, tangent_north = enu_displacement(center, spec.tangency_position)
    circle = PylonSpiralPath(
        name=spec.name,
        center=center,
        radius_m=spec.radius_m,
        start_bearing_rad=math.atan2(tangent_east, tangent_north),
        sweep_rad=math.tau,
        start_altitude_m=spec.altitude_m,
        end_altitude_m=spec.altitude_m,
        point_count=spec.point_count,
        evidence=EvidenceKind.ASSUMPTION_DEPENDENT,
        citation=spec.source,
    )
    points = list(circle.points())
    points[0] = PathPoint(points[0].position, points[0].altitude_m, "short_downwind_circle_start")
    points[-1] = PathPoint(
        points[-1].position,
        points[-1].altitude_m,
        "short_downwind_circle_complete",
    )
    return PolylineReferencePath(
        name=spec.name,
        path_points=tuple(points),
        evidence=EvidenceKind.ASSUMPTION_DEPENDENT,
        citation=spec.source,
    )
