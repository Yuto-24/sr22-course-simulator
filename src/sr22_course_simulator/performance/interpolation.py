"""Dependency-free N-dimensional multilinear interpolation."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import product
from math import fsum, isfinite, prod

from sr22_course_simulator.performance.table import (
    PerformanceAxis,
    RectilinearPerformanceTable,
    TableDefinitionError,
    _flat_index,
)
from sr22_course_simulator.provenance import (
    Applicability,
    Coverage,
    EvidenceKind,
    GapKind,
    ModelGap,
    SourceCitation,
    SupportStatus,
)


class InterpolationError(ValueError):
    """Base class for invalid interpolation requests."""


class QueryDimensionError(InterpolationError):
    """Raised when a query omits an axis or supplies an unknown coordinate."""

    def __init__(
        self,
        *,
        table_id: str,
        missing: tuple[str, ...],
        unexpected: tuple[object, ...],
    ) -> None:
        self.table_id = table_id
        self.missing = missing
        self.unexpected = unexpected
        details: list[str] = []
        if missing:
            details.append(f"missing axes {missing!r}")
        if unexpected:
            details.append(f"unexpected coordinates {unexpected!r}")
        super().__init__(f"table {table_id!r} query has " + " and ".join(details))


class InvalidCoordinateError(InterpolationError):
    """Raised when a coordinate is not a finite real number."""

    def __init__(self, *, table_id: str, axis_name: str, value: object) -> None:
        self.table_id = table_id
        self.axis_name = axis_name
        self.value = value
        super().__init__(
            f"table {table_id!r} coordinate for axis {axis_name!r} "
            "must be a finite real number"
        )


class OutOfDomainError(InterpolationError):
    """A structured rejection of a request outside a canonical source domain."""

    evidence = EvidenceKind.OUT_OF_DOMAIN

    def __init__(
        self,
        *,
        table_id: str,
        axis_name: str,
        requested: float,
        lower: float,
        upper: float,
        unit: str,
    ) -> None:
        self.table_id = table_id
        self.axis_name = axis_name
        self.requested = requested
        self.lower = lower
        self.upper = upper
        self.unit = unit
        description = (
            f"table {table_id!r} axis {axis_name!r} request {requested} {unit} "
            f"is outside source domain [{lower}, {upper}] {unit}"
        )
        self.coverage = Coverage(
            status=SupportStatus.OUT_OF_DOMAIN,
            evidence=(EvidenceKind.OUT_OF_DOMAIN,),
            gaps=(
                ModelGap(
                    kind=GapKind.OUT_OF_DOMAIN,
                    description=description,
                    quantity=axis_name,
                ),
            ),
        )
        super().__init__(description)


def _require_nonempty_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _finite_query_coordinate(
    value: object,
    *,
    table_id: str,
    axis_name: str,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidCoordinateError(
            table_id=table_id,
            axis_name=axis_name,
            value=value,
        )
    result = float(value)
    if not isfinite(result):
        raise InvalidCoordinateError(
            table_id=table_id,
            axis_name=axis_name,
            value=value,
        )
    return result


@dataclass(frozen=True, slots=True)
class PerformanceResult:
    """A performance value plus its source and derivation status."""

    quantity: str
    value: float
    unit: str
    evidence: EvidenceKind
    table_id: str
    query: tuple[tuple[str, float], ...]
    citation: SourceCitation
    applicability: Applicability

    def __post_init__(self) -> None:
        _require_nonempty_text(self.quantity, "quantity")
        _require_nonempty_text(self.unit, "unit")
        _require_nonempty_text(self.table_id, "table_id")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("performance result value must be a real number")
        value = float(self.value)
        if not isfinite(value):
            raise ValueError("performance result value must be finite")
        if not isinstance(self.evidence, EvidenceKind) or self.evidence not in (
            EvidenceKind.POH_TABLE_VALUE,
            EvidenceKind.POH_INTERPOLATED,
        ):
            raise ValueError(
                "performance result evidence must be poh_table_value or "
                "poh_interpolated"
            )
        if not isinstance(self.citation, SourceCitation):
            raise ValueError("citation must be a SourceCitation")
        if not isinstance(self.applicability, Applicability):
            raise ValueError("applicability must be an Applicability")

        try:
            raw_query = tuple(self.query)
        except TypeError as exc:
            raise ValueError("query must be a sequence of (axis, value) pairs") from exc
        query: list[tuple[str, float]] = []
        for item in raw_query:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("query items must be (axis, value) tuples")
            name, coordinate = item
            _require_nonempty_text(name, "query axis name")
            if (
                isinstance(coordinate, bool)
                or not isinstance(coordinate, (int, float))
                or not isfinite(float(coordinate))
            ):
                raise ValueError("query coordinate must be a finite real number")
            query.append((name, float(coordinate)))
        if len({name for name, _ in query}) != len(query):
            raise ValueError("query axis names must be unique")

        object.__setattr__(self, "value", value)
        object.__setattr__(self, "query", tuple(query))

    @property
    def is_source_node(self) -> bool:
        return self.evidence is EvidenceKind.POH_TABLE_VALUE

    @property
    def coverage(self) -> Coverage:
        return Coverage(
            status=SupportStatus.SUPPORTED,
            evidence=(self.evidence,),
        )


@dataclass(frozen=True, slots=True)
class _AxisBracket:
    lower_index: int
    upper_index: int
    upper_weight: float

    @property
    def is_exact(self) -> bool:
        return self.lower_index == self.upper_index


def _bracket(
    *,
    table_id: str,
    axis: PerformanceAxis,
    coordinate: float,
) -> _AxisBracket:
    if coordinate < axis.lower_bound or coordinate > axis.upper_bound:
        raise OutOfDomainError(
            table_id=table_id,
            axis_name=axis.name,
            requested=coordinate,
            lower=axis.lower_bound,
            upper=axis.upper_bound,
            unit=axis.unit,
        )

    upper_index = bisect_left(axis.values, coordinate)
    if upper_index < len(axis.values) and axis.values[upper_index] == coordinate:
        return _AxisBracket(upper_index, upper_index, 0.0)

    # Strict domain checks above and exact boundary handling guarantee two
    # neighboring nodes here, including for non-uniform axes.
    lower_index = upper_index - 1
    lower_value = axis.values[lower_index]
    upper_value = axis.values[upper_index]
    upper_weight = (coordinate - lower_value) / (upper_value - lower_value)
    return _AxisBracket(lower_index, upper_index, upper_weight)


def multilinear_interpolate(
    table: RectilinearPerformanceTable,
    point: Mapping[str, float],
) -> PerformanceResult:
    """Interpolate a canonical table without extrapolation.

    A query at an exact Cartesian source node bypasses interpolation arithmetic
    and returns the stored float directly.  There is intentionally no tolerance
    based snapping and no extrapolation option.
    """

    if not isinstance(table, RectilinearPerformanceTable):
        raise TypeError("table must be a RectilinearPerformanceTable")
    if not isinstance(point, Mapping):
        raise TypeError("point must be a mapping from axis name to coordinate")

    required_names = tuple(axis.name for axis in table.axes)
    provided_names = tuple(point.keys())
    missing = tuple(name for name in required_names if name not in point)
    unexpected = tuple(
        sorted((name for name in provided_names if name not in required_names), key=str)
    )
    if missing or unexpected:
        raise QueryDimensionError(
            table_id=table.table_id,
            missing=missing,
            unexpected=unexpected,
        )

    coordinates = tuple(
        _finite_query_coordinate(
            point[axis.name],
            table_id=table.table_id,
            axis_name=axis.name,
        )
        for axis in table.axes
    )
    brackets = tuple(
        _bracket(table_id=table.table_id, axis=axis, coordinate=coordinate)
        for axis, coordinate in zip(table.axes, coordinates, strict=True)
    )
    query = tuple(
        (axis.name, coordinate)
        for axis, coordinate in zip(table.axes, coordinates, strict=True)
    )

    if all(bracket.is_exact for bracket in brackets):
        value = table.value_at(bracket.lower_index for bracket in brackets)
        evidence = EvidenceKind.POH_TABLE_VALUE
    else:
        choices: list[tuple[tuple[int, float], ...]] = []
        for bracket in brackets:
            if bracket.is_exact:
                choices.append(((bracket.lower_index, 1.0),))
            else:
                choices.append(
                    (
                        (bracket.lower_index, 1.0 - bracket.upper_weight),
                        (bracket.upper_index, bracket.upper_weight),
                    )
                )

        weighted_values: list[float] = []
        for corner in product(*choices):
            indices = tuple(index for index, _ in corner)
            weight = prod(axis_weight for _, axis_weight in corner)
            weighted_values.append(table.value_at(indices) * weight)
        value = fsum(weighted_values)
        evidence = EvidenceKind.POH_INTERPOLATED

    return PerformanceResult(
        quantity=table.output_name,
        value=value,
        unit=table.output_unit,
        evidence=evidence,
        table_id=table.table_id,
        query=query,
        citation=table.citation,
        applicability=table.applicability,
    )


@dataclass(frozen=True, slots=True)
class DerivedPerformanceGrid:
    """A reproducible sampled grid derived from one canonical source table."""

    source_table_id: str
    axes: tuple[PerformanceAxis, ...]
    output_name: str
    output_unit: str
    values: tuple[float, ...]
    evidence: tuple[EvidenceKind, ...]
    citation: SourceCitation
    applicability: Applicability
    interpolation_method: str = "multilinear"

    def __post_init__(self) -> None:
        _require_nonempty_text(self.source_table_id, "source_table_id")
        _require_nonempty_text(self.output_name, "output_name")
        _require_nonempty_text(self.output_unit, "output_unit")
        _require_nonempty_text(self.interpolation_method, "interpolation_method")
        try:
            axes = tuple(self.axes)
            values = tuple(self.values)
            evidence = tuple(self.evidence)
        except TypeError as exc:
            raise ValueError("derived grid axes, values, and evidence must be sequences") from exc
        if not axes or not all(isinstance(axis, PerformanceAxis) for axis in axes):
            raise ValueError("derived grid axes must contain PerformanceAxis objects")
        if len({axis.name for axis in axes}) != len(axes):
            raise ValueError("derived grid axis names must be unique")
        expected = prod(len(axis.values) for axis in axes)
        if len(values) != expected or len(evidence) != expected:
            raise ValueError(
                f"derived grid shape {tuple(len(axis.values) for axis in axes)} "
                f"requires {expected} values and evidence entries"
            )
        normalized_values: list[float] = []
        for value in values:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(float(value))
            ):
                raise ValueError("derived grid values must be finite real numbers")
            normalized_values.append(float(value))
        if not all(
            isinstance(item, EvidenceKind)
            and item in (EvidenceKind.POH_TABLE_VALUE, EvidenceKind.POH_INTERPOLATED)
            for item in evidence
        ):
            raise ValueError("derived grid has an invalid evidence entry")
        if not isinstance(self.citation, SourceCitation):
            raise ValueError("citation must be a SourceCitation")
        if not isinstance(self.applicability, Applicability):
            raise ValueError("applicability must be an Applicability")
        object.__setattr__(self, "axes", axes)
        object.__setattr__(self, "values", tuple(normalized_values))
        object.__setattr__(self, "evidence", evidence)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(len(axis.values) for axis in self.axes)

    def value_at(self, indices: Iterable[int]) -> float:
        return self.values[
            _flat_index(
                indices,
                self.shape,
                owner=f"derived grid from {self.source_table_id!r}",
            )
        ]

    def evidence_at(self, indices: Iterable[int]) -> EvidenceKind:
        return self.evidence[
            _flat_index(
                indices,
                self.shape,
                owner=f"derived grid from {self.source_table_id!r}",
            )
        ]

    def coverage_at(self, indices: Iterable[int]) -> Coverage:
        return Coverage(
            status=SupportStatus.SUPPORTED,
            evidence=(self.evidence_at(indices),),
        )


def derive_grid(
    table: RectilinearPerformanceTable,
    axes: Iterable[PerformanceAxis],
) -> DerivedPerformanceGrid:
    """Sample ``table`` on new in-domain axes without changing canonical data."""

    if not isinstance(table, RectilinearPerformanceTable):
        raise TypeError("table must be a RectilinearPerformanceTable")
    try:
        derived_axes = tuple(axes)
    except TypeError as exc:
        raise TypeError("axes must be an iterable of PerformanceAxis") from exc
    if len(derived_axes) != len(table.axes):
        raise TableDefinitionError(
            f"derived grid for {table.table_id!r} requires {len(table.axes)} axes, "
            f"got {len(derived_axes)}"
        )
    if not all(isinstance(axis, PerformanceAxis) for axis in derived_axes):
        raise TableDefinitionError("derived grid axes must be PerformanceAxis objects")
    for source_axis, derived_axis in zip(table.axes, derived_axes, strict=True):
        if derived_axis.name != source_axis.name:
            raise TableDefinitionError(
                f"derived axis name {derived_axis.name!r} does not match source "
                f"axis {source_axis.name!r}"
            )
        if derived_axis.unit != source_axis.unit:
            raise TableDefinitionError(
                f"derived axis {derived_axis.name!r} unit {derived_axis.unit!r} "
                f"does not match source unit {source_axis.unit!r}"
            )

    results = tuple(
        multilinear_interpolate(
            table,
            dict(zip((axis.name for axis in derived_axes), coordinates, strict=True)),
        )
        for coordinates in product(*(axis.values for axis in derived_axes))
    )
    return DerivedPerformanceGrid(
        source_table_id=table.table_id,
        axes=derived_axes,
        output_name=table.output_name,
        output_unit=table.output_unit,
        values=tuple(result.value for result in results),
        evidence=tuple(result.evidence for result in results),
        citation=table.citation,
        applicability=table.applicability,
    )
