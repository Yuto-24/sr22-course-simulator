"""Canonical performance tables and source-domain interpolation."""

from sr22_course_simulator.performance.datasets import (
    bundled_poh_table_names,
    load_bundled_poh_table,
)
from sr22_course_simulator.performance.cruise import (
    CruiseConfiguration,
    CruisePerformanceResult,
    CruiseTableCompatibilityError,
    CruiseTrueAirspeed,
    ManifoldPressureSolution,
    PohCruiseQuery,
    SourcedKtasCorrection,
    load_bundled_cruise_query,
)

from sr22_course_simulator.performance.interpolation import (
    DerivedPerformanceGrid,
    InterpolationError,
    InvalidCoordinateError,
    OutOfDomainError,
    PerformanceResult,
    QueryDimensionError,
    derive_grid,
    multilinear_interpolate,
)
from sr22_course_simulator.performance.loader import (
    CANONICAL_TABLE_SCHEMA_VERSION,
    PerformanceTableLoadError,
    load_performance_table,
    performance_table_from_mapping,
)
from sr22_course_simulator.performance.table import (
    PerformanceAxis,
    RectilinearPerformanceTable,
    TableDefinitionError,
)

__all__ = [
    "CANONICAL_TABLE_SCHEMA_VERSION",
    "CruiseConfiguration",
    "CruisePerformanceResult",
    "CruiseTableCompatibilityError",
    "CruiseTrueAirspeed",
    "DerivedPerformanceGrid",
    "InterpolationError",
    "InvalidCoordinateError",
    "ManifoldPressureSolution",
    "OutOfDomainError",
    "PerformanceAxis",
    "PerformanceResult",
    "PerformanceTableLoadError",
    "PohCruiseQuery",
    "QueryDimensionError",
    "RectilinearPerformanceTable",
    "TableDefinitionError",
    "SourcedKtasCorrection",
    "derive_grid",
    "bundled_poh_table_names",
    "load_performance_table",
    "load_bundled_poh_table",
    "load_bundled_cruise_query",
    "multilinear_interpolate",
    "performance_table_from_mapping",
]
