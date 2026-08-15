"""Initial and time-varying aircraft state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from sr22_course_simulator.aircraft.input import FlapSetting
from sr22_course_simulator.aircraft.loading import Loading
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation
from sr22_course_simulator.units import radians_to_degrees, wrap_radians_2pi


class AirspeedKind(str, Enum):
    INDICATED = "ias"
    CALIBRATED = "cas"
    TRUE = "tas"
    UNSPECIFIED = "unspecified"


@dataclass(frozen=True, slots=True)
class GeoPosition:
    latitude_deg: float
    longitude_deg: float

    def __post_init__(self) -> None:
        lat = float(self.latitude_deg)
        lon = float(self.longitude_deg)
        if not math.isfinite(lat) or not -90.0 <= lat <= 90.0:
            raise ValidationError("latitude_deg must be finite and in [-90, 90]")
        if not math.isfinite(lon) or not -180.0 <= lon <= 180.0:
            raise ValidationError("longitude_deg must be finite and in [-180, 180]")
        object.__setattr__(self, "latitude_deg", lat)
        object.__setattr__(self, "longitude_deg", lon)


@dataclass(frozen=True, slots=True)
class InitialState:
    """Initial kinematic state plus loading/fuel information."""

    time_s: float
    position: GeoPosition
    altitude_m: float
    heading_true_rad: float
    true_airspeed_mps: float
    loading: Loading
    initial_fuel_mass_kg: float

    def __post_init__(self) -> None:
        finite = {
            "time_s": self.time_s,
            "altitude_m": self.altitude_m,
            "heading_true_rad": self.heading_true_rad,
            "true_airspeed_mps": self.true_airspeed_mps,
            "initial_fuel_mass_kg": self.initial_fuel_mass_kg,
        }
        for name, value in finite.items():
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValidationError(f"{name} must be finite")
        if self.true_airspeed_mps <= 0.0:
            raise ValidationError("true_airspeed_mps must be positive")
        if self.initial_fuel_mass_kg < 0.0:
            raise ValidationError("initial_fuel_mass_kg must be non-negative")
        if not isinstance(self.loading, Loading):
            raise ValidationError("loading must be a Loading")
        object.__setattr__(self, "time_s", float(self.time_s))
        object.__setattr__(self, "altitude_m", float(self.altitude_m))
        object.__setattr__(self, "heading_true_rad", wrap_radians_2pi(self.heading_true_rad))
        object.__setattr__(self, "true_airspeed_mps", float(self.true_airspeed_mps))
        object.__setattr__(self, "initial_fuel_mass_kg", float(self.initial_fuel_mass_kg))

    @property
    def initial_weight_kg(self) -> float:
        return self.loading.gross_mass_kg(self.initial_fuel_mass_kg)


@dataclass(frozen=True, slots=True)
class AircraftState:
    """A single time-indexed state in a :class:`Trajectory`."""

    time_s: float
    position: GeoPosition
    altitude_m: float
    heading_true_rad: float
    track_true_rad: float
    true_airspeed_mps: float
    ground_speed_mps: float
    vertical_speed_mps: float
    pitch_rad: float
    bank_rad: float
    power_fraction: float
    flap: FlapSetting
    fuel_remaining_kg: float
    fuel_burned_kg: float
    weight_kg: float
    accumulated_turn_rad: float
    evidence: tuple[EvidenceKind, ...] = ()
    source_citations: tuple[SourceCitation, ...] = ()

    def __post_init__(self) -> None:
        numeric_fields = (
            "time_s",
            "altitude_m",
            "heading_true_rad",
            "track_true_rad",
            "true_airspeed_mps",
            "ground_speed_mps",
            "vertical_speed_mps",
            "pitch_rad",
            "bank_rad",
            "power_fraction",
            "fuel_remaining_kg",
            "fuel_burned_kg",
            "weight_kg",
            "accumulated_turn_rad",
        )
        for name in numeric_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValidationError(f"{name} must be finite")
        for name in (
            "true_airspeed_mps",
            "ground_speed_mps",
            "fuel_remaining_kg",
            "fuel_burned_kg",
            "weight_kg",
        ):
            if getattr(self, name) < 0.0:
                raise ValidationError(f"{name} must be non-negative")
        if not 0.0 <= self.power_fraction <= 1.0:
            raise ValidationError("power_fraction must be in [0, 1]")
        object.__setattr__(self, "heading_true_rad", wrap_radians_2pi(self.heading_true_rad))
        object.__setattr__(self, "track_true_rad", wrap_radians_2pi(self.track_true_rad))
        object.__setattr__(self, "evidence", tuple(dict.fromkeys(self.evidence)))
        object.__setattr__(self, "source_citations", tuple(dict.fromkeys(self.source_citations)))
        if any(not isinstance(item, SourceCitation) for item in self.source_citations):
            raise ValidationError("source_citations must contain SourceCitation values")

    @property
    def heading_true_deg(self) -> float:
        return radians_to_degrees(self.heading_true_rad)

    @property
    def track_true_deg(self) -> float:
        return radians_to_degrees(self.track_true_rad)
