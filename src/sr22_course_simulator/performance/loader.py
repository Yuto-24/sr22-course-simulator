"""Strict loader for versioned canonical performance-table JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sr22_course_simulator.performance.table import (
    PerformanceAxis,
    RectilinearPerformanceTable,
    TableDefinitionError,
)
from sr22_course_simulator.provenance import (
    Applicability,
    ApplicabilityField,
    SourceCitation,
)


CANONICAL_TABLE_SCHEMA_VERSION = 1


class PerformanceTableLoadError(ValueError):
    """Raised when a canonical JSON document is malformed or unsupported."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PerformanceTableLoadError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise PerformanceTableLoadError(f"non-standard JSON numeric constant {value!r}")


def _object(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PerformanceTableLoadError(f"{context} must be a JSON object")
    if not all(isinstance(key, str) for key in value):
        raise PerformanceTableLoadError(f"{context} keys must be strings")
    return value  # type: ignore[return-value]


def _array(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise PerformanceTableLoadError(f"{context} must be a JSON array")
    return value


def _keys(
    value: Mapping[str, object],
    *,
    context: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unknown = sorted(actual - required - optional)
    if missing:
        raise PerformanceTableLoadError(f"{context} is missing keys {missing!r}")
    if unknown:
        raise PerformanceTableLoadError(f"{context} has unknown keys {unknown!r}")


def _optional_text_array(
    value: Mapping[str, object],
    key: str,
    *,
    context: str,
) -> tuple[object, ...]:
    if key not in value:
        return ()
    return tuple(_array(value[key], f"{context}.{key}"))


def _performance_table_from_mapping(
    document: Mapping[str, object],
) -> RectilinearPerformanceTable:
    root = _object(document, "canonical table")
    _keys(
        root,
        context="canonical table",
        required=frozenset(
            {
                "schema_version",
                "table_id",
                "axes",
                "output",
                "values",
                "citation",
                "applicability",
            }
        ),
    )
    schema_version = root["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != CANONICAL_TABLE_SCHEMA_VERSION
    ):
        raise PerformanceTableLoadError(
            f"unsupported canonical table schema_version {schema_version!r}; "
            f"expected {CANONICAL_TABLE_SCHEMA_VERSION}"
        )

    axes_data = _array(root["axes"], "canonical table.axes")
    axes: list[PerformanceAxis] = []
    for index, raw_axis in enumerate(axes_data):
        context = f"canonical table.axes[{index}]"
        axis = _object(raw_axis, context)
        _keys(
            axis,
            context=context,
            required=frozenset({"name", "unit", "values"}),
        )
        axes.append(
            PerformanceAxis(
                name=axis["name"],  # type: ignore[arg-type]
                unit=axis["unit"],  # type: ignore[arg-type]
                values=tuple(_array(axis["values"], f"{context}.values")),  # type: ignore[arg-type]
            )
        )

    output = _object(root["output"], "canonical table.output")
    _keys(
        output,
        context="canonical table.output",
        required=frozenset({"name", "unit"}),
    )

    raw_citation = _object(root["citation"], "canonical table.citation")
    citation_optional = frozenset(
        {
            "revision",
            "effective_date",
            "chapter",
            "section",
            "page",
            "table",
            "extraction_method",
            "transformations",
            "notes",
        }
    )
    _keys(
        raw_citation,
        context="canonical table.citation",
        required=frozenset({"document_title"}),
        optional=citation_optional,
    )
    citation = SourceCitation(
        document_title=raw_citation["document_title"],  # type: ignore[arg-type]
        revision=raw_citation.get("revision"),  # type: ignore[arg-type]
        effective_date=raw_citation.get("effective_date"),  # type: ignore[arg-type]
        chapter=raw_citation.get("chapter"),  # type: ignore[arg-type]
        section=raw_citation.get("section"),  # type: ignore[arg-type]
        page=raw_citation.get("page"),  # type: ignore[arg-type]
        table=raw_citation.get("table"),  # type: ignore[arg-type]
        extraction_method=raw_citation.get("extraction_method"),  # type: ignore[arg-type]
        transformations=_optional_text_array(
            raw_citation,
            "transformations",
            context="canonical table.citation",
        ),  # type: ignore[arg-type]
        notes=_optional_text_array(
            raw_citation,
            "notes",
            context="canonical table.citation",
        ),  # type: ignore[arg-type]
    )

    raw_applicability = _object(
        root["applicability"], "canonical table.applicability"
    )
    _keys(
        raw_applicability,
        context="canonical table.applicability",
        required=frozenset({"aircraft_model"}),
        optional=frozenset({"configuration", "conditions"}),
    )
    configuration: list[ApplicabilityField] = []
    if "configuration" in raw_applicability:
        raw_configuration = _array(
            raw_applicability["configuration"],
            "canonical table.applicability.configuration",
        )
        for index, raw_field in enumerate(raw_configuration):
            context = f"canonical table.applicability.configuration[{index}]"
            field = _object(raw_field, context)
            _keys(
                field,
                context=context,
                required=frozenset({"name", "value"}),
                optional=frozenset({"unit"}),
            )
            configuration.append(
                ApplicabilityField(
                    name=field["name"],  # type: ignore[arg-type]
                    value=field["value"],  # type: ignore[arg-type]
                    unit=field.get("unit"),  # type: ignore[arg-type]
                )
            )
    conditions: tuple[object, ...] = ()
    if "conditions" in raw_applicability:
        conditions = tuple(
            _array(
                raw_applicability["conditions"],
                "canonical table.applicability.conditions",
            )
        )
    applicability = Applicability(
        aircraft_model=raw_applicability["aircraft_model"],  # type: ignore[arg-type]
        configuration=tuple(configuration),
        conditions=conditions,  # type: ignore[arg-type]
    )

    return RectilinearPerformanceTable(
        table_id=root["table_id"],  # type: ignore[arg-type]
        axes=tuple(axes),
        output_name=output["name"],  # type: ignore[arg-type]
        output_unit=output["unit"],  # type: ignore[arg-type]
        values=tuple(_array(root["values"], "canonical table.values")),  # type: ignore[arg-type]
        citation=citation,
        applicability=applicability,
    )


def performance_table_from_mapping(
    document: Mapping[str, object],
) -> RectilinearPerformanceTable:
    """Validate and construct a canonical table from decoded JSON data."""

    try:
        return _performance_table_from_mapping(document)
    except PerformanceTableLoadError:
        raise
    except (TableDefinitionError, TypeError, ValueError) as exc:
        raise PerformanceTableLoadError(
            f"invalid canonical performance table mapping: {exc}"
        ) from exc


def load_performance_table(path: str | Path) -> RectilinearPerformanceTable:
    """Load one canonical table from strict UTF-8 JSON."""

    source_path = Path(path)
    try:
        with source_path.open("r", encoding="utf-8") as stream:
            document = json.load(
                stream,
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_nonstandard_constant,
            )
        return performance_table_from_mapping(document)
    except PerformanceTableLoadError:
        raise
    except json.JSONDecodeError as exc:
        raise PerformanceTableLoadError(
            f"invalid JSON in {source_path}: {exc.msg} at line {exc.lineno}, "
            f"column {exc.colno}"
        ) from exc
    except (TableDefinitionError, TypeError, ValueError) as exc:
        raise PerformanceTableLoadError(
            f"invalid canonical performance table {source_path}: {exc}"
        ) from exc
