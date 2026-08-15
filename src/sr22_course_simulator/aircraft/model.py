"""Honest quasi-steady aircraft-response interfaces.

The package intentionally supplies no built-in SR22 numerical performance data.
The runnable model in this module is explicitly assumption-dependent and accepts
all of its operating point and gains from the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from sr22_course_simulator.aircraft.input import FlapSetting, FlightInput
from sr22_course_simulator.aircraft.state import AircraftState
from sr22_course_simulator.environment import Environment
from sr22_course_simulator.errors import UnsupportedModelError, ValidationError
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation


@dataclass(frozen=True, slots=True)
class PerformanceSnapshot:
    true_airspeed_mps: float
    fuel_flow_kg_s: float
    evidence: tuple[EvidenceKind, ...]
    notes: tuple[str, ...] = ()
    source_citations: tuple[SourceCitation, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.true_airspeed_mps) or self.true_airspeed_mps <= 0.0:
            raise ValidationError("resolved true airspeed must be finite and positive")
        if not math.isfinite(self.fuel_flow_kg_s) or self.fuel_flow_kg_s < 0.0:
            raise ValidationError("resolved fuel flow must be finite and non-negative")
        object.__setattr__(self, "evidence", tuple(dict.fromkeys(self.evidence)))
        object.__setattr__(self, "notes", tuple(self.notes))
        object.__setattr__(self, "source_citations", tuple(dict.fromkeys(self.source_citations)))
        if any(not isinstance(item, SourceCitation) for item in self.source_citations):
            raise ValidationError("source_citations must contain SourceCitation values")


@dataclass(frozen=True, slots=True)
class QuasiSteadyResponse:
    true_airspeed_mps: float
    flight_path_angle_rad: float
    fuel_flow_kg_s: float
    evidence: tuple[EvidenceKind, ...]
    notes: tuple[str, ...] = ()
    source_citations: tuple[SourceCitation, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.true_airspeed_mps) or self.true_airspeed_mps <= 0.0:
            raise ValidationError("response TAS must be finite and positive")
        if not math.isfinite(self.flight_path_angle_rad) or not (
            -math.pi / 2 < self.flight_path_angle_rad < math.pi / 2
        ):
            raise ValidationError("flight-path angle must lie strictly between -pi/2 and pi/2")
        if not math.isfinite(self.fuel_flow_kg_s) or self.fuel_flow_kg_s < 0.0:
            raise ValidationError("response fuel flow must be finite and non-negative")
        object.__setattr__(self, "evidence", tuple(dict.fromkeys(self.evidence)))
        object.__setattr__(self, "notes", tuple(self.notes))
        object.__setattr__(self, "source_citations", tuple(dict.fromkeys(self.source_citations)))
        if any(not isinstance(item, SourceCitation) for item in self.source_citations):
            raise ValidationError("source_citations must contain SourceCitation values")


@runtime_checkable
class SteadyPerformanceProvider(Protocol):
    def resolve(
        self,
        state: AircraftState,
        flight_input: FlightInput,
        environment: Environment,
    ) -> PerformanceSnapshot:
        """Resolve source-supported or explicitly assumed TAS and fuel flow."""


@runtime_checkable
class LongitudinalClosure(Protocol):
    def flight_path_angle_rad(
        self,
        state: AircraftState,
        flight_input: FlightInput,
        performance: PerformanceSnapshot,
        environment: Environment,
    ) -> tuple[float, tuple[EvidenceKind, ...], tuple[str, ...]]:
        """Close the source gap between Pitch and flight-path angle."""


@runtime_checkable
class AircraftResponseModel(Protocol):
    name: str

    def resolve(
        self,
        state: AircraftState,
        flight_input: FlightInput,
        environment: Environment,
    ) -> QuasiSteadyResponse:
        """Resolve the supported quasi-steady response for one integration step."""


@dataclass(frozen=True, slots=True)
class AssumptionDomain:
    minimum_pitch_rad: float
    maximum_pitch_rad: float
    minimum_bank_rad: float
    maximum_bank_rad: float
    minimum_power_fraction: float
    maximum_power_fraction: float
    supported_flaps: tuple[FlapSetting, ...]

    def __post_init__(self) -> None:
        bounds = (
            self.minimum_pitch_rad,
            self.maximum_pitch_rad,
            self.minimum_bank_rad,
            self.maximum_bank_rad,
            self.minimum_power_fraction,
            self.maximum_power_fraction,
        )
        if any(not math.isfinite(float(value)) for value in bounds):
            raise ValidationError("assumption-domain bounds must be finite")
        if self.minimum_pitch_rad > self.maximum_pitch_rad:
            raise ValidationError("minimum_pitch_rad exceeds maximum_pitch_rad")
        if self.minimum_bank_rad > self.maximum_bank_rad:
            raise ValidationError("minimum_bank_rad exceeds maximum_bank_rad")
        if self.minimum_power_fraction > self.maximum_power_fraction:
            raise ValidationError("minimum_power_fraction exceeds maximum_power_fraction")
        if not 0.0 <= self.minimum_power_fraction <= self.maximum_power_fraction <= 1.0:
            raise ValidationError("power domain must lie within [0, 1]")
        object.__setattr__(self, "supported_flaps", tuple(self.supported_flaps))
        if not self.supported_flaps:
            raise ValidationError("at least one supported flap setting is required")

    def check(self, flight_input: FlightInput) -> None:
        if not self.minimum_pitch_rad <= flight_input.pitch_rad <= self.maximum_pitch_rad:
            raise UnsupportedModelError("Pitch is outside the declared assumption-model domain")
        if not self.minimum_bank_rad <= flight_input.bank_rad <= self.maximum_bank_rad:
            raise UnsupportedModelError("Bank is outside the declared assumption-model domain")
        if not self.minimum_power_fraction <= flight_input.power_fraction <= self.maximum_power_fraction:
            raise UnsupportedModelError("PWR is outside the declared assumption-model domain")
        if flight_input.flap not in self.supported_flaps:
            raise UnsupportedModelError("Flap is outside the declared assumption-model domain")


@dataclass(frozen=True, slots=True)
class AssumedSteadyPointProvider:
    """Caller-parameterized, assumption-dependent local performance closure.

    This class is for examples, synthetic tests and an explicitly calibrated
    local operating region.  It is not shipped as SR22 POH performance.

    ``TAS = reference + power_gain * dPWR - pitch_gain * dPitch``
    ``fuel_flow = zero_power_flow + power_flow_gain * PWR``
    """

    domain: AssumptionDomain
    reference_true_airspeed_mps: float
    reference_power_fraction: float
    reference_pitch_rad: float
    tas_per_power_fraction_mps: float
    tas_per_pitch_rad_mps: float
    zero_power_fuel_flow_kg_s: float
    fuel_flow_per_power_fraction_kg_s: float

    def __post_init__(self) -> None:
        for name in (
            "reference_true_airspeed_mps",
            "reference_power_fraction",
            "reference_pitch_rad",
            "tas_per_power_fraction_mps",
            "tas_per_pitch_rad_mps",
            "zero_power_fuel_flow_kg_s",
            "fuel_flow_per_power_fraction_kg_s",
        ):
            if not math.isfinite(float(getattr(self, name))):
                raise ValidationError(f"{name} must be finite")
        if self.reference_true_airspeed_mps <= 0.0:
            raise ValidationError("reference_true_airspeed_mps must be positive")
        if not 0.0 <= self.reference_power_fraction <= 1.0:
            raise ValidationError("reference_power_fraction must be in [0, 1]")
        if self.zero_power_fuel_flow_kg_s < 0.0 or self.fuel_flow_per_power_fraction_kg_s < 0.0:
            raise ValidationError("fuel-flow parameters must be non-negative")

    def resolve(
        self,
        state: AircraftState,
        flight_input: FlightInput,
        environment: Environment,
    ) -> PerformanceSnapshot:
        self.domain.check(flight_input)
        tas = (
            self.reference_true_airspeed_mps
            + self.tas_per_power_fraction_mps
            * (flight_input.power_fraction - self.reference_power_fraction)
            - self.tas_per_pitch_rad_mps * (flight_input.pitch_rad - self.reference_pitch_rad)
        )
        fuel_flow = (
            self.zero_power_fuel_flow_kg_s
            + self.fuel_flow_per_power_fraction_kg_s * flight_input.power_fraction
        )
        if tas <= 0.0:
            raise UnsupportedModelError(
                "assumption model resolved non-positive TAS; operating point is outside usable coverage"
            )
        return PerformanceSnapshot(
            true_airspeed_mps=tas,
            fuel_flow_kg_s=fuel_flow,
            evidence=(EvidenceKind.ASSUMED,),
            notes=(
                "Caller-supplied local steady-point relation; not SR22 POH data.",
                "No transient response, bank drag correction, or arbitrary-flight-envelope claim.",
            ),
        )


@dataclass(frozen=True, slots=True)
class AssumedAngleOfAttackClosure:
    """Assume a fixed reference angle of attack: gamma = pitch - alpha_ref."""

    reference_angle_of_attack_rad: float

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.reference_angle_of_attack_rad)):
            raise ValidationError("reference_angle_of_attack_rad must be finite")

    def flight_path_angle_rad(
        self,
        state: AircraftState,
        flight_input: FlightInput,
        performance: PerformanceSnapshot,
        environment: Environment,
    ) -> tuple[float, tuple[EvidenceKind, ...], tuple[str, ...]]:
        return (
            flight_input.pitch_rad - self.reference_angle_of_attack_rad,
            (EvidenceKind.ASSUMED,),
            ("Fixed-angle-of-attack longitudinal closure; source or calibration required.",),
        )


@dataclass(frozen=True, slots=True)
class QuasiSteadyAircraftModel:
    name: str
    performance: SteadyPerformanceProvider
    longitudinal_closure: LongitudinalClosure

    def resolve(
        self,
        state: AircraftState,
        flight_input: FlightInput,
        environment: Environment,
    ) -> QuasiSteadyResponse:
        performance = self.performance.resolve(state, flight_input, environment)
        gamma, closure_evidence, closure_notes = self.longitudinal_closure.flight_path_angle_rad(
            state,
            flight_input,
            performance,
            environment,
        )
        return QuasiSteadyResponse(
            true_airspeed_mps=performance.true_airspeed_mps,
            flight_path_angle_rad=gamma,
            fuel_flow_kg_s=performance.fuel_flow_kg_s,
            evidence=performance.evidence + closure_evidence,
            notes=performance.notes + closure_notes,
            source_citations=performance.source_citations,
        )


@dataclass(frozen=True, slots=True)
class SourceDataRequiredPerformanceProvider:
    """Production-safe placeholder used while canonical POH tables are absent."""

    required_source: str

    def resolve(
        self,
        state: AircraftState,
        flight_input: FlightInput,
        environment: Environment,
    ) -> PerformanceSnapshot:
        raise UnsupportedModelError(
            "No source-backed performance table covers this request",
            gap=f"Source data required: {self.required_source}",
        )
