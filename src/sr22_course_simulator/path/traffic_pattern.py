"""Wind-independent straight-segment airport traffic-pattern geometry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from sr22_course_simulator.airport import AirportSpec, RunwaySpec
from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.geometry import displace_position
from sr22_course_simulator.path.reference import PathPoint, PolylineReferencePath
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation
from sr22_course_simulator.units import feet_to_metres, nautical_miles_to_metres


class PatternSide(StrEnum):
    """Pattern side relative to the landing runway direction."""

    LEFT = "left"
    RIGHT = "right"


class PatternLabel(StrEnum):
    """Geographic display label for a pattern."""

    NORTH = "north"
    SOUTH = "south"


@dataclass(frozen=True, slots=True)
class TrafficPatternSpec:
    """Source-derived parameters for a geometric traffic pattern.

    This object does not accept wind or aircraft-dynamics inputs. Its output is
    a ``ReferencePath``, not a simulated ``Trajectory``.
    """

    airport: AirportSpec
    runway: RunwaySpec
    side: PatternSide
    label: PatternLabel
    altitude_ft: float
    downwind_offset_nm: float
    base_extension_nm: float
    crosswind_extension_nm: float
    source: SourceCitation

    def __post_init__(self) -> None:
        if not isinstance(self.airport, AirportSpec):
            raise ValidationError("traffic-pattern airport must be an AirportSpec")
        if not isinstance(self.runway, RunwaySpec):
            raise ValidationError("traffic-pattern runway must be a RunwaySpec")
        if self.runway not in self.airport.runways:
            raise ValidationError("traffic-pattern runway must belong to its airport")
        if not isinstance(self.side, PatternSide):
            raise ValidationError("traffic-pattern side must be PatternSide")
        if not isinstance(self.label, PatternLabel):
            raise ValidationError("traffic-pattern label must be PatternLabel")
        if not isinstance(self.source, SourceCitation):
            raise ValidationError("traffic-pattern source must be a SourceCitation")

        for field_name in (
            "altitude_ft",
            "downwind_offset_nm",
            "base_extension_nm",
            "crosswind_extension_nm",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool):
                raise ValidationError(f"{field_name} must be finite")
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"{field_name} must be finite") from exc
            if not math.isfinite(numeric):
                raise ValidationError(f"{field_name} must be finite")
            if numeric < 0.0:
                raise ValidationError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, numeric)

    @property
    def name(self) -> str:
        """Return a stable human-readable path name."""

        return (
            f"{self.airport.icao} RWY{self.runway.designation} "
            f"{self.label.value.upper()} Normal Traffic Pattern"
        )


def _position_from_runway_center(
    runway: RunwaySpec,
    *,
    along_m: float,
    lateral_m: float,
    side: PatternSide,
) -> GeoPosition:
    """Resolve runway-axis coordinates from the computed RWY Center Point."""

    runway_east, runway_north = runway.runway_unit_vector
    if side is PatternSide.LEFT:
        normal_east, normal_north = runway.left_normal_unit_vector
    else:
        normal_east, normal_north = runway.right_normal_unit_vector
    return displace_position(
        runway.center_point,
        east_m=runway_east * along_m + normal_east * lateral_m,
        north_m=runway_north * along_m + normal_north * lateral_m,
    )


def generate_traffic_pattern(spec: TrafficPatternSpec) -> PolylineReferencePath:
    """Generate a six-point, straight-segment traffic ``ReferencePath``.

    Along-runway and lateral coordinates are computed from the runway true
    bearing and its threshold midpoint. The ARP is never used in this function.
    """

    runway = spec.runway
    half_runway_m = runway.measured_length_m / 2.0
    downwind_offset_m = nautical_miles_to_metres(spec.downwind_offset_nm)
    base_extension_m = nautical_miles_to_metres(spec.base_extension_nm)
    crosswind_extension_m = nautical_miles_to_metres(spec.crosswind_extension_nm)
    altitude_m = feet_to_metres(spec.altitude_ft)

    landing_threshold_station_m = -half_runway_m
    departure_station_m = half_runway_m + crosswind_extension_m
    base_station_m = landing_threshold_station_m - base_extension_m

    coordinates = (
        ("departure_reference", departure_station_m, 0.0),
        ("crosswind", departure_station_m, downwind_offset_m),
        ("downwind", landing_threshold_station_m, downwind_offset_m),
        ("base", base_station_m, downwind_offset_m),
        ("final", base_station_m, 0.0),
        ("threshold_return", landing_threshold_station_m, 0.0),
    )
    points = tuple(
        PathPoint(
            position=_position_from_runway_center(
                runway,
                along_m=along_m,
                lateral_m=lateral_m,
                side=spec.side,
            ),
            altitude_m=altitude_m,
            label=label,
        )
        for label, along_m, lateral_m in coordinates
    )
    return PolylineReferencePath(
        name=spec.name,
        path_points=points,
        evidence=EvidenceKind.PROCEDURE_PATH_CONSTRAINT,
        citation=spec.source,
    )
