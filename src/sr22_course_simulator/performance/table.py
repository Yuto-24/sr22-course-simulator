"""Immutable canonical rectilinear performance-table representation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, prod
from typing import Iterable

from sr22_course_simulator.provenance import (
    Applicability,
    Coverage,
    EvidenceKind,
    SourceCitation,
    SupportStatus,
)


class TableDefinitionError(ValueError):
    """Raised when canonical table data is incomplete or internally inconsistent."""


def _require_nonempty_text(value: object, field_name: str) -> None:
    """Validate that a field contains nonblank text.
    
    Parameters:
        value (object): Value to validate.
        field_name (str): Name of the field used in the error message.
    
    Raises:
        TableDefinitionError: If the value is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        raise TableDefinitionError(f"{field_name} must be a non-empty string")


def _finite_float(value: object, field_name: str) -> float:
    """
    Convert a numeric value to a finite floating-point number.
    
    Parameters:
        value (object): Value to validate and convert.
        field_name (str): Name used in validation error messages.
    
    Returns:
        float: The finite floating-point representation of `value`.
    
    Raises:
        TableDefinitionError: If `value` is a boolean, is not numeric, or is not finite.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TableDefinitionError(f"{field_name} must be a real number")
    result = float(value)
    if not isfinite(result):
        raise TableDefinitionError(f"{field_name} must be finite")
    return result


def _as_tuple(value: object, field_name: str) -> tuple[object, ...]:
    """
    Convert a non-string sequence to an immutable tuple.
    
    Parameters:
        value (object): The value to convert.
        field_name (str): The field name used in validation errors.
    
    Returns:
        tuple[object, ...]: The converted tuple.
    
    Raises:
        TableDefinitionError: If the value is a string, bytes object, or not iterable.
    """
    if isinstance(value, (str, bytes)):
        raise TableDefinitionError(f"{field_name} must be a sequence")
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TableDefinitionError(f"{field_name} must be a sequence") from exc


def _flat_index(
    indices: Iterable[int],
    shape: tuple[int, ...],
    *,
    owner: str,
) -> int:
    """
    Convert multidimensional integer indices into a row-major flat index.
    
    Parameters:
        indices (Iterable[int]): Integer index for each dimension.
        shape (tuple[int, ...]): Size of each dimension.
        owner (str): Name included in validation error messages.
    
    Returns:
        int: The row-major flat index.
    
    Raises:
        IndexError: If the indices are not iterable integers, have the wrong
            dimensionality, or fall outside the corresponding dimension bounds.
    """
    try:
        index_tuple = tuple(indices)
    except TypeError as exc:
        raise IndexError(f"{owner}: indices must be an iterable of integers") from exc
    if len(index_tuple) != len(shape):
        raise IndexError(
            f"{owner}: expected {len(shape)} indices, got {len(index_tuple)}"
        )

    flat_index = 0
    for dimension, (index, size) in enumerate(zip(index_tuple, shape, strict=True)):
        if isinstance(index, bool) or not isinstance(index, int):
            raise IndexError(f"{owner}: index for dimension {dimension} must be an int")
        if index < 0 or index >= size:
            raise IndexError(
                f"{owner}: index {index} outside dimension {dimension} range "
                f"[0, {size - 1}]"
            )
        flat_index = flat_index * size + index
    return flat_index


@dataclass(frozen=True, slots=True)
class PerformanceAxis:
    """A numeric independent variable in the units printed by the source."""

    name: str
    unit: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        """
        Validate and normalize the axis definition after initialization.
        
        Raises:
            TableDefinitionError: If the axis name or unit is blank, the values are
                missing or invalid, or the values are not strictly increasing.
        """
        _require_nonempty_text(self.name, "axis name")
        _require_nonempty_text(self.unit, f"unit for axis {self.name!r}")
        raw_values = _as_tuple(self.values, f"values for axis {self.name!r}")
        if not raw_values:
            raise TableDefinitionError(f"axis {self.name!r} must have at least one value")
        values = tuple(
            _finite_float(item, f"axis {self.name!r} value") for item in raw_values
        )
        for lower, upper in zip(values, values[1:]):
            if upper <= lower:
                raise TableDefinitionError(
                    f"axis {self.name!r} values must be strictly increasing"
                )
        object.__setattr__(self, "values", values)

    @property
    def lower_bound(self) -> float:
        """Return the smallest value on the axis."""
        return self.values[0]

    @property
    def upper_bound(self) -> float:
        """Return the largest value on the axis."""
        return self.values[-1]


@dataclass(frozen=True, slots=True)
class RectilinearPerformanceTable:
    """One source-backed dependent quantity on a complete rectilinear grid.

    ``values`` uses C/row-major ordering: the final axis varies fastest.  The
    class represents canonical source nodes only; generated dense grids use a
    different type in :mod:`sr22_course_simulator.performance.interpolation`.
    """

    table_id: str
    axes: tuple[PerformanceAxis, ...]
    output_name: str
    output_unit: str
    values: tuple[float, ...]
    citation: SourceCitation
    applicability: Applicability

    def __post_init__(self) -> None:
        """
        Validate and normalize the table definition after initialization.
        
        Raises:
            TableDefinitionError: If the table metadata, axes, values, citation, or applicability
                is invalid or inconsistent.
        """
        _require_nonempty_text(self.table_id, "table_id")
        _require_nonempty_text(self.output_name, "output_name")
        _require_nonempty_text(self.output_unit, "output_unit")

        raw_axes = _as_tuple(self.axes, "axes")
        if not raw_axes:
            raise TableDefinitionError("a rectilinear table must have at least one axis")
        if not all(isinstance(axis, PerformanceAxis) for axis in raw_axes):
            raise TableDefinitionError("axes must contain only PerformanceAxis objects")
        axes = tuple(raw_axes)  # type: ignore[assignment]
        axis_names = [axis.name for axis in axes]
        if len(axis_names) != len(set(axis_names)):
            raise TableDefinitionError("axis names must be unique")

        raw_values = _as_tuple(self.values, "values")
        expected_value_count = prod(len(axis.values) for axis in axes)
        if len(raw_values) != expected_value_count:
            raise TableDefinitionError(
                f"table {self.table_id!r} shape {tuple(len(axis.values) for axis in axes)} "
                f"requires {expected_value_count} values, got {len(raw_values)}"
            )
        values = tuple(
            _finite_float(item, f"table {self.table_id!r} output value")
            for item in raw_values
        )

        if not isinstance(self.citation, SourceCitation):
            raise TableDefinitionError("citation must be a SourceCitation")
        if not isinstance(self.applicability, Applicability):
            raise TableDefinitionError("applicability must be an Applicability")

        object.__setattr__(self, "axes", axes)
        object.__setattr__(self, "values", values)

    @property
    def shape(self) -> tuple[int, ...]:
        """Return the number of values along each table axis."""
        return tuple(len(axis.values) for axis in self.axes)

    @property
    def evidence(self) -> EvidenceKind:
        """Evidence kind of every value stored in the canonical table."""

        return EvidenceKind.POH_TABLE_VALUE

    @property
    def coverage(self) -> Coverage:
        """
        Describe support for canonical table nodes using the table-value evidence.
        
        Returns:
            Coverage: Supported coverage backed by `POH_TABLE_VALUE` evidence.
        """

        return Coverage(
            status=SupportStatus.SUPPORTED,
            evidence=(EvidenceKind.POH_TABLE_VALUE,),
        )

    def value_at(self, indices: Iterable[int]) -> float:
        """
        Return the table value at an N-dimensional integer index.
        
        Parameters:
            indices (Iterable[int]): Zero-based index for each table axis.
        
        Returns:
            float: The value at the specified index.
        """

        return self.values[
            _flat_index(indices, self.shape, owner=f"table {self.table_id!r}")
        ]
