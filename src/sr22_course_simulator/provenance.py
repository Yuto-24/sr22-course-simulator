"""Source provenance and evidence labels shared across the simulator.

The source citation and the derivation applied to a value are deliberately
separate concepts.  For example, an interpolated POH result still cites the
POH table, but its evidence kind is ``poh_interpolated`` rather than
``poh_table_value``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import TypeAlias


class EvidenceKind(StrEnum):
    """Semantic/provenance labels used by source-backed and modeled values."""

    PROCEDURE_TARGET = "procedure_target"
    PROCEDURE_LIMIT = "procedure_limit"
    PROCEDURE_NOMINAL = "procedure_nominal"
    PROCEDURE_INITIAL_SETTING = "procedure_initial_setting"
    PROCEDURE_CONTROL_RELATIONSHIP = "procedure_control_relationship"
    PROCEDURE_PATH_CONSTRAINT = "procedure_path_constraint"
    ADVISORY_REFERENCE = "advisory_reference"
    POH_TABLE_VALUE = "poh_table_value"
    POH_INTERPOLATED = "poh_interpolated"
    PHYSICS_DERIVED = "physics_derived"
    CALIBRATED = "calibrated"
    ASSUMED = "assumed"
    ASSUMPTION_DEPENDENT = "assumption_dependent"
    UNSUPPORTED = "unsupported"
    OUT_OF_DOMAIN = "out_of_domain"


class SupportStatus(StrEnum):
    """Whether the active model can support a requested operating point."""

    SUPPORTED = "supported"
    ASSUMPTION_DEPENDENT = "assumption_dependent"
    UNSUPPORTED = "unsupported"
    OUT_OF_DOMAIN = "out_of_domain"


class GapKind(StrEnum):
    """Why a requested relationship or operating point is not supported."""

    SOURCE_DATA_MISSING = "source_data_missing"
    SOURCE_NOT_STATED = "source_not_stated"
    NOT_IMPLEMENTED = "not_implemented"
    OUT_OF_DOMAIN = "out_of_domain"


MetadataScalar: TypeAlias = str | int | float | bool


def _require_nonempty_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_optional_text(value: object, field_name: str) -> None:
    if value is not None:
        _require_nonempty_text(value, field_name)


def _immutable_text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence of strings, not text")
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a sequence of strings") from exc
    for item in items:
        _require_nonempty_text(item, f"{field_name} item")
    return items


@dataclass(frozen=True, slots=True)
class SourceCitation:
    """Location and transcription metadata for a source data set."""

    document_title: str
    revision: str | None = None
    effective_date: str | None = None
    chapter: str | None = None
    section: str | None = None
    page: str | None = None
    table: str | None = None
    extraction_method: str | None = None
    transformations: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_text(self.document_title, "document_title")
        for field_name in (
            "revision",
            "effective_date",
            "chapter",
            "section",
            "page",
            "table",
            "extraction_method",
        ):
            _validate_optional_text(getattr(self, field_name), field_name)
        object.__setattr__(
            self,
            "transformations",
            _immutable_text_tuple(self.transformations, "transformations"),
        )
        object.__setattr__(self, "notes", _immutable_text_tuple(self.notes, "notes"))


@dataclass(frozen=True, slots=True)
class ApplicabilityField:
    """A fixed source condition that must not become an interpolation axis."""

    name: str
    value: MetadataScalar
    unit: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty_text(self.name, "applicability field name")
        if not isinstance(self.value, (str, int, float, bool)):
            raise ValueError(
                "applicability field value must be a string, number, or boolean"
            )
        if isinstance(self.value, str):
            _require_nonempty_text(self.value, "applicability field value")
        elif isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("numeric applicability field value must be finite")
        _validate_optional_text(self.unit, "applicability field unit")


@dataclass(frozen=True, slots=True)
class Applicability:
    """Aircraft/configuration conditions under which source data applies.

    Conditions are intentionally retained as metadata here rather than being
    interpreted by the generic interpolation engine.  A performance provider
    is responsible for selecting a table whose applicability has been checked.
    """

    aircraft_model: str
    configuration: tuple[ApplicabilityField, ...] = ()
    conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_text(self.aircraft_model, "aircraft_model")
        if isinstance(self.configuration, (str, bytes)):
            raise ValueError("configuration must be a sequence of ApplicabilityField")
        try:
            configuration = tuple(self.configuration)
        except TypeError as exc:
            raise ValueError(
                "configuration must be a sequence of ApplicabilityField"
            ) from exc
        if not all(isinstance(item, ApplicabilityField) for item in configuration):
            raise ValueError("configuration items must be ApplicabilityField instances")
        names = [item.name for item in configuration]
        if len(names) != len(set(names)):
            raise ValueError("applicability configuration field names must be unique")
        object.__setattr__(self, "configuration", configuration)
        object.__setattr__(
            self,
            "conditions",
            _immutable_text_tuple(self.conditions, "conditions"),
        )


@dataclass(frozen=True, slots=True)
class ModelGap:
    """An explicit missing relationship, source fact, or model capability."""

    kind: GapKind
    description: str
    quantity: str | None = None
    citation: SourceCitation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GapKind):
            raise ValueError("kind must be a GapKind")
        _require_nonempty_text(self.description, "model gap description")
        _validate_optional_text(self.quantity, "model gap quantity")
        if self.citation is not None and not isinstance(self.citation, SourceCitation):
            raise ValueError("model gap citation must be a SourceCitation or None")


@dataclass(frozen=True, slots=True)
class Coverage:
    """Model coverage metadata that composes conservatively.

    Combining coverage never upgrades fidelity.  The least-supported input
    status wins, while evidence and explicit gaps are retained in first-seen
    order without duplicates.
    """

    status: SupportStatus
    evidence: tuple[EvidenceKind, ...] = ()
    gaps: tuple[ModelGap, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, SupportStatus):
            raise ValueError("coverage status must be a SupportStatus")
        if isinstance(self.evidence, (str, bytes)):
            raise ValueError("coverage evidence must be a sequence of EvidenceKind")
        if isinstance(self.gaps, (str, bytes)):
            raise ValueError("coverage gaps must be a sequence of ModelGap")
        try:
            evidence = tuple(self.evidence)
            gaps = tuple(self.gaps)
        except TypeError as exc:
            raise ValueError("coverage evidence and gaps must be sequences") from exc
        if not all(isinstance(item, EvidenceKind) for item in evidence):
            raise ValueError("coverage evidence items must be EvidenceKind values")
        if not all(isinstance(item, ModelGap) for item in gaps):
            raise ValueError("coverage gaps must be ModelGap instances")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "gaps", gaps)

    @classmethod
    def combine(cls, *coverages: Coverage) -> Coverage:
        """Combine dependencies using the most conservative support status."""

        if not coverages:
            raise ValueError("at least one Coverage is required")
        if not all(isinstance(item, Coverage) for item in coverages):
            raise ValueError("all combined items must be Coverage instances")
        rank = {
            SupportStatus.SUPPORTED: 0,
            SupportStatus.ASSUMPTION_DEPENDENT: 1,
            SupportStatus.UNSUPPORTED: 2,
            SupportStatus.OUT_OF_DOMAIN: 3,
        }
        status = max((item.status for item in coverages), key=rank.__getitem__)

        evidence: list[EvidenceKind] = []
        gaps: list[ModelGap] = []
        for coverage in coverages:
            for item in coverage.evidence:
                if item not in evidence:
                    evidence.append(item)
            for item in coverage.gaps:
                if item not in gaps:
                    gaps.append(item)
        return cls(status=status, evidence=tuple(evidence), gaps=tuple(gaps))
