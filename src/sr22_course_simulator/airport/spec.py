"""Source-backed airport and runway master data.

Airport reference points (ARP) are retained for reference and source checks.
Runway geometry is anchored to the midpoint of the two runway thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.geometry import distance_m
from sr22_course_simulator.provenance import SourceCitation
from sr22_course_simulator.units import wrap_degrees_360


_AIP_DMS_PATTERN = re.compile(
    r"^(?P<degrees>\d{2,3})(?P<minutes>\d{2})(?P<seconds>\d{2}(?:\.\d+)?)(?P<hemisphere>[NSEW])$",
    re.IGNORECASE,
)


def parse_aip_dms(value: str) -> float:
    """Parse a compact AIP coordinate such as ``315234.26N``.

    Latitude uses two degree digits and longitude uses three. North and east
    are positive; south and west are negative.
    """

    if not isinstance(value, str):
        raise ValidationError("AIP DMS coordinate must be text")
    normalized = value.strip().upper()
    match = _AIP_DMS_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValidationError(f"invalid AIP DMS coordinate: {value!r}")

    hemisphere = match.group("hemisphere")
    degree_text = match.group("degrees")
    expected_degree_digits = 2 if hemisphere in {"N", "S"} else 3
    if len(degree_text) != expected_degree_digits:
        raise ValidationError(
            f"{hemisphere} coordinate must use {expected_degree_digits} degree digits"
        )

    degrees = int(degree_text)
    minutes = int(match.group("minutes"))
    seconds = float(match.group("seconds"))
    maximum_degrees = 90 if hemisphere in {"N", "S"} else 180
    if minutes >= 60 or seconds >= 60.0:
        raise ValidationError("AIP DMS minutes and seconds must be below 60")
    if degrees > maximum_degrees or (
        degrees == maximum_degrees and (minutes != 0 or seconds != 0.0)
    ):
        raise ValidationError(f"AIP DMS coordinate exceeds {maximum_degrees} degrees")

    decimal = degrees + minutes / 60.0 + seconds / 3_600.0
    return -decimal if hemisphere in {"S", "W"} else decimal


def _finite(value: float, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} must be finite")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be finite") from exc
    if not math.isfinite(numeric):
        raise ValidationError(f"{field_name} must be finite")
    return numeric


@dataclass(frozen=True, slots=True)
class RunwaySpec:
    """One landing direction of a physical runway.

    ``threshold_a`` is the landing threshold for ``designation`` and
    ``threshold_b`` is the reciprocal/departure-end threshold. The reciprocal
    direction is represented as another ``RunwaySpec`` with the thresholds
    reversed, allowing direction-specific true bearings without hiding the
    shared physical geometry.
    """

    designation: str
    true_bearing_deg: float
    threshold_a: GeoPosition
    threshold_b: GeoPosition
    threshold_elevation_a_ft: float
    threshold_elevation_b_ft: float
    declared_length_m: float
    width_m: float
    source: SourceCitation

    def __post_init__(self) -> None:
        if not isinstance(self.designation, str):
            raise ValidationError("runway designation must be text")
        designation = self.designation.strip().upper()
        if not designation:
            raise ValidationError("runway designation must not be empty")
        if not isinstance(self.threshold_a, GeoPosition) or not isinstance(
            self.threshold_b, GeoPosition
        ):
            raise ValidationError("runway thresholds must be GeoPosition values")
        if self.threshold_a == self.threshold_b:
            raise ValidationError("runway thresholds must be distinct")
        if not isinstance(self.source, SourceCitation):
            raise ValidationError("runway source must be a SourceCitation")

        bearing = _finite(self.true_bearing_deg, "true_bearing_deg")
        elevation_a = _finite(
            self.threshold_elevation_a_ft, "threshold_elevation_a_ft"
        )
        elevation_b = _finite(
            self.threshold_elevation_b_ft, "threshold_elevation_b_ft"
        )
        declared_length = _finite(self.declared_length_m, "declared_length_m")
        width = _finite(self.width_m, "width_m")
        if declared_length <= 0.0 or width <= 0.0:
            raise ValidationError("runway dimensions must be positive")

        object.__setattr__(self, "designation", designation)
        object.__setattr__(self, "true_bearing_deg", wrap_degrees_360(bearing))
        object.__setattr__(self, "threshold_elevation_a_ft", elevation_a)
        object.__setattr__(self, "threshold_elevation_b_ft", elevation_b)
        object.__setattr__(self, "declared_length_m", declared_length)
        object.__setattr__(self, "width_m", width)

    @property
    def center_point(self) -> GeoPosition:
        """Return ``(THR A + THR B) / 2`` for runway geometry."""

        return GeoPosition(
            latitude_deg=(
                self.threshold_a.latitude_deg + self.threshold_b.latitude_deg
            )
            / 2.0,
            longitude_deg=(
                self.threshold_a.longitude_deg + self.threshold_b.longitude_deg
            )
            / 2.0,
        )

    @property
    def measured_length_m(self) -> float:
        """Return the threshold-to-threshold length from source coordinates."""

        return distance_m(self.threshold_a, self.threshold_b)

    @property
    def runway_unit_vector(self) -> tuple[float, float]:
        """Return the true-bearing unit vector as ``(east, north)``."""

        bearing_rad = math.radians(self.true_bearing_deg)
        return math.sin(bearing_rad), math.cos(bearing_rad)

    @property
    def left_normal_unit_vector(self) -> tuple[float, float]:
        """Return the left normal as ``(east, north)`` for this landing direction."""

        east, north = self.runway_unit_vector
        return -north, east

    @property
    def right_normal_unit_vector(self) -> tuple[float, float]:
        """Return the right normal as ``(east, north)`` for this landing direction."""

        east, north = self.left_normal_unit_vector
        return -east, -north


@dataclass(frozen=True, slots=True)
class AirportSpec:
    """AIP-derived airport master data with an explicitly reference-only ARP."""

    icao: str
    name: str
    reference_point: GeoPosition
    elevation_ft: float
    magnetic_variation_deg: float
    magnetic_variation_epoch_year: float
    annual_change_deg_per_year: float
    source: SourceCitation
    runways: tuple[RunwaySpec, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.icao, str) or not isinstance(self.name, str):
            raise ValidationError("airport ICAO and name must be text")
        icao = self.icao.strip().upper()
        name = self.name.strip()
        if len(icao) != 4 or not icao.isalnum():
            raise ValidationError("airport ICAO must contain four alphanumeric characters")
        if not name:
            raise ValidationError("airport name must not be empty")
        if not isinstance(self.reference_point, GeoPosition):
            raise ValidationError("airport reference_point must be a GeoPosition")
        if not isinstance(self.source, SourceCitation):
            raise ValidationError("airport source must be a SourceCitation")

        runways = tuple(self.runways)
        if not runways or any(not isinstance(item, RunwaySpec) for item in runways):
            raise ValidationError("airport runways must contain RunwaySpec values")
        designations = [runway.designation for runway in runways]
        if len(set(designations)) != len(designations):
            raise ValidationError("runway designations must be unique within an airport")

        object.__setattr__(self, "icao", icao)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "elevation_ft", _finite(self.elevation_ft, "elevation_ft"))
        object.__setattr__(
            self,
            "magnetic_variation_deg",
            _finite(self.magnetic_variation_deg, "magnetic_variation_deg"),
        )
        object.__setattr__(
            self,
            "magnetic_variation_epoch_year",
            _finite(
                self.magnetic_variation_epoch_year,
                "magnetic_variation_epoch_year",
            ),
        )
        object.__setattr__(
            self,
            "annual_change_deg_per_year",
            _finite(self.annual_change_deg_per_year, "annual_change_deg_per_year"),
        )
        object.__setattr__(self, "runways", runways)

    def runway(self, designation: str) -> RunwaySpec:
        """Return one directional runway by designation."""

        if not isinstance(designation, str):
            raise ValidationError("runway designation must be text")
        normalized = designation.strip().upper()
        for runway in self.runways:
            if runway.designation == normalized:
                return runway
        raise ValidationError(f"airport {self.icao} has no runway {designation!r}")

    def variation_at(self, year: float) -> float:
        """Return magnetic variation in degrees; east is positive."""

        requested_year = _finite(year, "year")
        return self.magnetic_variation_deg + self.annual_change_deg_per_year * (
            requested_year - self.magnetic_variation_epoch_year
        )

    def true_to_magnetic(self, true_bearing_deg: float, *, year: float) -> float:
        """Convert a true bearing to magnetic without affecting path geometry."""

        true_bearing = _finite(true_bearing_deg, "true_bearing_deg")
        return wrap_degrees_360(true_bearing - self.variation_at(year))
