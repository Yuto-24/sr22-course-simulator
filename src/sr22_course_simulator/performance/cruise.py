"""Narrow POH cruise queries for the bundled 2,000-ft / 2500-RPM slice.

The three canonical tables use manifold pressure and ISA deviation as their
published axes.  This module accepts a requested percent power by inverting the
monotonic power table piecewise-linearly, then queries power, KTAS, and
volumetric fuel flow at the same solved operating point.

Fuel flow remains in US gallons per hour.  This module intentionally provides
no mass-flow conversion and no simulation performance provider because no fuel
density is supplied by these tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isclose, isfinite

from sr22_course_simulator.performance.datasets import load_bundled_poh_table
from sr22_course_simulator.performance.interpolation import (
    OutOfDomainError,
    PerformanceResult,
    multilinear_interpolate,
)
from sr22_course_simulator.performance.table import RectilinearPerformanceTable
from sr22_course_simulator.provenance import (
    Applicability,
    ApplicabilityField,
    EvidenceKind,
    SourceCitation,
)


_POWER_TABLE_FILE = "cruise_2000ft_2500rpm_power.json"
_KTAS_TABLE_FILE = "cruise_2000ft_2500rpm_ktas.json"
_FUEL_FLOW_TABLE_FILE = "cruise_2000ft_2500rpm_fuel_flow.json"

_MAP_AXIS_NAME = "manifold_pressure_inhg"
_MAP_UNIT = "inHg"
_ISA_AXIS_NAME = "isa_deviation_deg_c"
_ISA_UNIT = "degC"

_POWER_OUTPUT = ("power", "percent")
_KTAS_OUTPUT = ("true_airspeed", "kt")
_FUEL_FLOW_OUTPUT = ("fuel_flow", "US gal/h")

_CORE_APPLICABILITY_FIELDS = frozenset(
    {"weight", "pressure_altitude", "engine_speed"}
)
_EXPECTED_CORE_APPLICABILITY = {
    "weight": ApplicabilityField("weight", 3400.0, "lb"),
    "pressure_altitude": ApplicabilityField("pressure_altitude", 2000.0, "ft"),
    "engine_speed": ApplicabilityField("engine_speed", 2500.0, "RPM"),
}
_FAIRING_BASELINE_FIELD = "canonical_wheel_fairing_baseline"
_FAIRING_BASELINE_VALUE = "installed"
_TARGET_FAIRING_FIELD = "nose_wheel_pant_fairing"
_TARGET_FAIRING_VALUE = "removed"
_NOSE_WHEEL_CORRECTION_NOTE = (
    "POH note: subtract 10 KTAS when the nose-wheel pant/fairing is removed"
)
_NOSE_WHEEL_CORRECTION_KTAS = -10.0


class CruiseTableCompatibilityError(ValueError):
    """Raised when tables cannot safely be composed into one cruise query."""


class CruiseConfiguration(StrEnum):
    """The explicitly selected interpretation of the published KTAS values."""

    POH_CANONICAL_BASELINE = "poh_canonical_baseline"
    TARGET_NOSE_WHEEL_PANT_REMOVED = "target_nose_wheel_pant_removed"


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite real number")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _citation_compatibility_key(citation: SourceCitation) -> tuple[object, ...]:
    """Return source identity while allowing output-specific citation notes."""

    return (
        citation.document_title,
        citation.revision,
        citation.effective_date,
        citation.chapter,
        citation.section,
        citation.page,
        citation.table,
        citation.extraction_method,
        citation.transformations,
    )


def _applicability_fields(
    applicability: Applicability,
) -> dict[str, ApplicabilityField]:
    return {item.name: item for item in applicability.configuration}


@dataclass(frozen=True, slots=True)
class ManifoldPressureSolution:
    """Traceable inverse solution of PWR(MAP, ISA deviation)."""

    value_inhg: float
    requested_power_percent: float
    isa_deviation_deg_c: float
    lower_map_inhg: float
    upper_map_inhg: float
    lower_power: PerformanceResult
    upper_power: PerformanceResult
    evidence: EvidenceKind

    def __post_init__(self) -> None:
        for name in (
            "value_inhg",
            "requested_power_percent",
            "isa_deviation_deg_c",
            "lower_map_inhg",
            "upper_map_inhg",
        ):
            object.__setattr__(self, name, _finite_number(getattr(self, name), name))
        if self.lower_map_inhg > self.value_inhg or self.value_inhg > self.upper_map_inhg:
            raise ValueError("solved manifold pressure must lie inside its source bracket")
        if not isinstance(self.lower_power, PerformanceResult) or not isinstance(
            self.upper_power, PerformanceResult
        ):
            raise ValueError("power brackets must be PerformanceResult instances")
        for result in (self.lower_power, self.upper_power):
            if (result.quantity, result.unit) != _POWER_OUTPUT:
                raise ValueError("power brackets must contain percent-power results")
        if not isinstance(self.evidence, EvidenceKind) or self.evidence not in (
            EvidenceKind.POH_TABLE_VALUE,
            EvidenceKind.POH_INTERPOLATED,
        ):
            raise ValueError("manifold-pressure evidence must be POH-backed")

    @property
    def citation(self) -> SourceCitation:
        return self.lower_power.citation

    @property
    def applicability(self) -> Applicability:
        return self.lower_power.applicability


@dataclass(frozen=True, slots=True)
class SourcedKtasCorrection:
    """The printed additive KTAS correction for the target fairing state."""

    delta_ktas: float
    baseline_configuration: ApplicabilityField
    target_configuration: ApplicabilityField
    citation: SourceCitation
    source_note: str
    evidence: EvidenceKind = field(
        default=EvidenceKind.POH_TABLE_VALUE,
        init=False,
    )

    def __post_init__(self) -> None:
        delta = _finite_number(self.delta_ktas, "delta_ktas")
        if delta != _NOSE_WHEEL_CORRECTION_KTAS:
            raise ValueError("the bundled source correction must be exactly -10 KTAS")
        if not isinstance(self.baseline_configuration, ApplicabilityField):
            raise ValueError("baseline_configuration must be an ApplicabilityField")
        if not isinstance(self.target_configuration, ApplicabilityField):
            raise ValueError("target_configuration must be an ApplicabilityField")
        if (
            self.baseline_configuration.name != _FAIRING_BASELINE_FIELD
            or self.baseline_configuration.value != _FAIRING_BASELINE_VALUE
        ):
            raise ValueError("invalid canonical wheel-fairing baseline")
        if (
            self.target_configuration.name != _TARGET_FAIRING_FIELD
            or self.target_configuration.value != _TARGET_FAIRING_VALUE
        ):
            raise ValueError("invalid target wheel-fairing configuration")
        if not isinstance(self.citation, SourceCitation):
            raise ValueError("citation must be a SourceCitation")
        if self.source_note != _NOSE_WHEEL_CORRECTION_NOTE:
            raise ValueError("the typed correction must retain the verified source note")
        object.__setattr__(self, "delta_ktas", delta)


@dataclass(frozen=True, slots=True)
class CruiseTrueAirspeed:
    """Canonical KTAS and any explicitly selected sourced correction."""

    canonical: PerformanceResult
    correction: SourcedKtasCorrection | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.canonical, PerformanceResult):
            raise ValueError("canonical must be a PerformanceResult")
        if (self.canonical.quantity, self.canonical.unit) != _KTAS_OUTPUT:
            raise ValueError("canonical airspeed must be a KTAS performance result")
        if self.correction is not None and not isinstance(
            self.correction, SourcedKtasCorrection
        ):
            raise ValueError("correction must be a SourcedKtasCorrection or None")

    @property
    def canonical_ktas(self) -> float:
        return self.canonical.value

    @property
    def effective_ktas(self) -> float:
        if self.correction is None:
            return self.canonical.value
        return self.canonical.value + self.correction.delta_ktas

    @property
    def is_corrected(self) -> bool:
        return self.correction is not None


@dataclass(frozen=True, slots=True)
class CruisePerformanceResult:
    """One common MAP/ISA cruise query with all source results retained."""

    configuration: CruiseConfiguration
    requested_power_percent: float
    isa_deviation_deg_c: float
    manifold_pressure: ManifoldPressureSolution
    power: PerformanceResult
    true_airspeed: CruiseTrueAirspeed
    fuel_flow: PerformanceResult

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, CruiseConfiguration):
            raise ValueError("configuration must be a CruiseConfiguration")
        requested_power = _finite_number(
            self.requested_power_percent, "requested_power_percent"
        )
        isa_deviation = _finite_number(
            self.isa_deviation_deg_c, "isa_deviation_deg_c"
        )
        if not isinstance(self.manifold_pressure, ManifoldPressureSolution):
            raise ValueError("manifold_pressure must be a ManifoldPressureSolution")
        if not isinstance(self.power, PerformanceResult):
            raise ValueError("power must be a PerformanceResult")
        if (self.power.quantity, self.power.unit) != _POWER_OUTPUT:
            raise ValueError("power result must contain percent power")
        if not isinstance(self.true_airspeed, CruiseTrueAirspeed):
            raise ValueError("true_airspeed must be a CruiseTrueAirspeed")
        if not isinstance(self.fuel_flow, PerformanceResult):
            raise ValueError("fuel_flow must be a PerformanceResult")
        if (self.fuel_flow.quantity, self.fuel_flow.unit) != _FUEL_FLOW_OUTPUT:
            raise ValueError("fuel flow must remain in US gallons per hour")
        if not isclose(self.power.value, requested_power, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("resolved source power does not match the requested power")
        expected_query = self.power.query
        if self.true_airspeed.canonical.query != expected_query:
            raise ValueError("KTAS was not queried at the solved power operating point")
        if self.fuel_flow.query != expected_query:
            raise ValueError("fuel flow was not queried at the solved power operating point")
        if self.configuration is CruiseConfiguration.POH_CANONICAL_BASELINE:
            if self.true_airspeed.correction is not None:
                raise ValueError("canonical cruise query must not apply a correction")
        elif self.true_airspeed.correction is None:
            raise ValueError("target-configuration query requires its sourced correction")
        object.__setattr__(self, "requested_power_percent", requested_power)
        object.__setattr__(self, "isa_deviation_deg_c", isa_deviation)

    @property
    def manifold_pressure_inhg(self) -> float:
        return self.manifold_pressure.value_inhg

    @property
    def canonical_ktas(self) -> float:
        return self.true_airspeed.canonical_ktas

    @property
    def effective_ktas(self) -> float:
        return self.true_airspeed.effective_ktas

    @property
    def fuel_flow_gph(self) -> float:
        """Return source volumetric flow; no fuel-density conversion is implied."""

        return self.fuel_flow.value


@dataclass(frozen=True, slots=True)
class PohCruiseQuery:
    """Validated composition of power, KTAS, and GPH canonical tables."""

    power_table: RectilinearPerformanceTable
    ktas_table: RectilinearPerformanceTable
    fuel_flow_table: RectilinearPerformanceTable

    def __post_init__(self) -> None:
        tables = (self.power_table, self.ktas_table, self.fuel_flow_table)
        if not all(isinstance(table, RectilinearPerformanceTable) for table in tables):
            raise CruiseTableCompatibilityError(
                "all cruise inputs must be RectilinearPerformanceTable instances"
            )
        self._validate_axes()
        self._validate_outputs()
        self._validate_citations()
        self._validate_applicability()
        self._validate_monotonic_power()

    @classmethod
    def from_bundled_tables(cls) -> PohCruiseQuery:
        """Load and validate the bundled verified 2,000-ft/2500-RPM slice."""

        return cls(
            power_table=load_bundled_poh_table(_POWER_TABLE_FILE),
            ktas_table=load_bundled_poh_table(_KTAS_TABLE_FILE),
            fuel_flow_table=load_bundled_poh_table(_FUEL_FLOW_TABLE_FILE),
        )

    def _validate_axes(self) -> None:
        expected_axis_identity = (
            (_MAP_AXIS_NAME, _MAP_UNIT),
            (_ISA_AXIS_NAME, _ISA_UNIT),
        )
        reference_axes = self.power_table.axes
        if tuple((axis.name, axis.unit) for axis in reference_axes) != expected_axis_identity:
            raise CruiseTableCompatibilityError(
                "cruise tables must use MAP [inHg] then ISA deviation [degC] axes"
            )
        for table in (self.ktas_table, self.fuel_flow_table):
            if table.axes != reference_axes:
                raise CruiseTableCompatibilityError(
                    "power, KTAS, and fuel-flow axes and nodes must match exactly"
                )

    def _validate_outputs(self) -> None:
        actual = (
            (self.power_table.output_name, self.power_table.output_unit),
            (self.ktas_table.output_name, self.ktas_table.output_unit),
            (self.fuel_flow_table.output_name, self.fuel_flow_table.output_unit),
        )
        expected = (_POWER_OUTPUT, _KTAS_OUTPUT, _FUEL_FLOW_OUTPUT)
        if actual != expected:
            raise CruiseTableCompatibilityError(
                f"cruise table outputs must be {expected!r}, got {actual!r}"
            )

    def _validate_citations(self) -> None:
        citation_keys = {
            _citation_compatibility_key(table.citation)
            for table in (self.power_table, self.ktas_table, self.fuel_flow_table)
        }
        if len(citation_keys) != 1:
            raise CruiseTableCompatibilityError(
                "cruise tables must cite the same document revision and table"
            )
        if _NOSE_WHEEL_CORRECTION_NOTE not in self.ktas_table.citation.notes:
            raise CruiseTableCompatibilityError(
                "KTAS citation does not retain the printed nose-wheel correction"
            )

    def _validate_applicability(self) -> None:
        tables = (self.power_table, self.ktas_table, self.fuel_flow_table)
        aircraft_models = {table.applicability.aircraft_model for table in tables}
        if len(aircraft_models) != 1:
            raise CruiseTableCompatibilityError(
                "cruise tables have incompatible aircraft applicability"
            )

        power_fields = _applicability_fields(self.power_table.applicability)
        ktas_fields = _applicability_fields(self.ktas_table.applicability)
        fuel_fields = _applicability_fields(self.fuel_flow_table.applicability)
        if set(power_fields) != _CORE_APPLICABILITY_FIELDS:
            raise CruiseTableCompatibilityError(
                "power table must declare weight, pressure altitude, and engine speed"
            )
        if power_fields != _EXPECTED_CORE_APPLICABILITY:
            raise CruiseTableCompatibilityError(
                "this query supports only the 3400-lb / 2,000-ft / 2500-RPM "
                "canonical slice"
            )
        if fuel_fields != power_fields:
            raise CruiseTableCompatibilityError(
                "power and fuel-flow applicability must match exactly"
            )
        if set(ktas_fields) != _CORE_APPLICABILITY_FIELDS | {
            _FAIRING_BASELINE_FIELD
        }:
            raise CruiseTableCompatibilityError(
                "KTAS applicability must add only the canonical fairing baseline"
            )
        for name, value in power_fields.items():
            if ktas_fields[name] != value:
                raise CruiseTableCompatibilityError(
                    f"KTAS applicability conflicts on {name!r}"
                )
        baseline = ktas_fields[_FAIRING_BASELINE_FIELD]
        if baseline.value != _FAIRING_BASELINE_VALUE or baseline.unit is not None:
            raise CruiseTableCompatibilityError(
                "KTAS canonical wheel-fairing baseline must be 'installed'"
            )

        power_conditions = set(self.power_table.applicability.conditions)
        fuel_conditions = set(self.fuel_flow_table.applicability.conditions)
        ktas_conditions = set(self.ktas_table.applicability.conditions)
        if fuel_conditions != power_conditions or not power_conditions <= ktas_conditions:
            raise CruiseTableCompatibilityError(
                "cruise table applicability conditions are incompatible"
            )

    def _validate_monotonic_power(self) -> None:
        map_count, isa_count = self.power_table.shape
        for isa_index in range(isa_count):
            powers = tuple(
                self.power_table.value_at((map_index, isa_index))
                for map_index in range(map_count)
            )
            if any(upper <= lower for lower, upper in zip(powers, powers[1:])):
                raise CruiseTableCompatibilityError(
                    "percent power must be strictly increasing with MAP at every "
                    "canonical ISA-deviation node"
                )

    def _solve_manifold_pressure(
        self,
        *,
        power_percent: float,
        isa_deviation_deg_c: float,
    ) -> ManifoldPressureSolution:
        map_axis, _ = self.power_table.axes
        curve = tuple(
            multilinear_interpolate(
                self.power_table,
                {
                    _MAP_AXIS_NAME: map_value,
                    _ISA_AXIS_NAME: isa_deviation_deg_c,
                },
            )
            for map_value in map_axis.values
        )
        lower_power = curve[0].value
        upper_power = curve[-1].value
        if power_percent < lower_power or power_percent > upper_power:
            raise OutOfDomainError(
                table_id=self.power_table.table_id,
                axis_name="power",
                requested=power_percent,
                lower=lower_power,
                upper=upper_power,
                unit="percent",
            )

        for index, result in enumerate(curve):
            if result.value == power_percent:
                map_value = map_axis.values[index]
                return ManifoldPressureSolution(
                    value_inhg=map_value,
                    requested_power_percent=power_percent,
                    isa_deviation_deg_c=isa_deviation_deg_c,
                    lower_map_inhg=map_value,
                    upper_map_inhg=map_value,
                    lower_power=result,
                    upper_power=result,
                    evidence=result.evidence,
                )

        for index, (lower_result, upper_result) in enumerate(
            zip(curve, curve[1:])
        ):
            if lower_result.value < power_percent < upper_result.value:
                lower_map = map_axis.values[index]
                upper_map = map_axis.values[index + 1]
                fraction = (power_percent - lower_result.value) / (
                    upper_result.value - lower_result.value
                )
                map_value = lower_map + fraction * (upper_map - lower_map)
                return ManifoldPressureSolution(
                    value_inhg=map_value,
                    requested_power_percent=power_percent,
                    isa_deviation_deg_c=isa_deviation_deg_c,
                    lower_map_inhg=lower_map,
                    upper_map_inhg=upper_map,
                    lower_power=lower_result,
                    upper_power=upper_result,
                    evidence=EvidenceKind.POH_INTERPOLATED,
                )
        raise RuntimeError("validated monotonic power curve did not bracket request")

    def _query(
        self,
        *,
        power_percent: float,
        isa_deviation_deg_c: float,
        configuration: CruiseConfiguration,
    ) -> CruisePerformanceResult:
        power = _finite_number(power_percent, "power_percent")
        isa_deviation = _finite_number(
            isa_deviation_deg_c, "isa_deviation_deg_c"
        )
        solution = self._solve_manifold_pressure(
            power_percent=power,
            isa_deviation_deg_c=isa_deviation,
        )
        point = {
            _MAP_AXIS_NAME: solution.value_inhg,
            _ISA_AXIS_NAME: isa_deviation,
        }
        power_result = multilinear_interpolate(self.power_table, point)
        ktas_result = multilinear_interpolate(self.ktas_table, point)
        fuel_flow_result = multilinear_interpolate(self.fuel_flow_table, point)

        correction: SourcedKtasCorrection | None = None
        if configuration is CruiseConfiguration.TARGET_NOSE_WHEEL_PANT_REMOVED:
            baseline = _applicability_fields(self.ktas_table.applicability)[
                _FAIRING_BASELINE_FIELD
            ]
            correction = SourcedKtasCorrection(
                delta_ktas=_NOSE_WHEEL_CORRECTION_KTAS,
                baseline_configuration=baseline,
                target_configuration=ApplicabilityField(
                    name=_TARGET_FAIRING_FIELD,
                    value=_TARGET_FAIRING_VALUE,
                ),
                citation=self.ktas_table.citation,
                source_note=_NOSE_WHEEL_CORRECTION_NOTE,
            )

        return CruisePerformanceResult(
            configuration=configuration,
            requested_power_percent=power,
            isa_deviation_deg_c=isa_deviation,
            manifold_pressure=solution,
            power=power_result,
            true_airspeed=CruiseTrueAirspeed(
                canonical=ktas_result,
                correction=correction,
            ),
            fuel_flow=fuel_flow_result,
        )

    def query_canonical(
        self,
        *,
        power_percent: float,
        isa_deviation_deg_c: float,
    ) -> CruisePerformanceResult:
        """Query unmodified POH table values for its printed baseline."""

        return self._query(
            power_percent=power_percent,
            isa_deviation_deg_c=isa_deviation_deg_c,
            configuration=CruiseConfiguration.POH_CANONICAL_BASELINE,
        )

    def query_target_configuration(
        self,
        *,
        power_percent: float,
        isa_deviation_deg_c: float,
    ) -> CruisePerformanceResult:
        """Query the project target with the sourced -10 KTAS correction."""

        return self._query(
            power_percent=power_percent,
            isa_deviation_deg_c=isa_deviation_deg_c,
            configuration=CruiseConfiguration.TARGET_NOSE_WHEEL_PANT_REMOVED,
        )


def load_bundled_cruise_query() -> PohCruiseQuery:
    """Return a validated query object for the bundled canonical table slice."""

    return PohCruiseQuery.from_bundled_tables()
