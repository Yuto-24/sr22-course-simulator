"""Source-semantic maneuver specifications, separate from advisory tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from sr22_course_simulator.aircraft.state import AirspeedKind
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.provenance import EvidenceKind, ModelGap, SourceCitation


class LimitDirection(str, Enum):
    MINIMUM = "minimum"
    MAXIMUM = "maximum"


class ControlChannel(str, Enum):
    PITCH = "pitch"
    BANK = "bank"
    POWER = "power"
    FLAP = "flap"


def _validate_quantity(
    *,
    quantity: str,
    value: float,
    unit: str,
    citation: SourceCitation,
) -> None:
    """Validate a quantitative semantic field and its source provenance.
    
    Parameters:
    	quantity (str): Name of the quantity.
    	value (float): Numeric quantity value.
    	unit (str): Unit associated with the quantity.
    	citation (SourceCitation): Source provenance for the quantity.
    
    Raises:
    	ValidationError: If the quantity or unit is empty, the value is Boolean or non-finite, or the citation is not a `SourceCitation`.
    """
    if not quantity.strip() or not unit.strip():
        raise ValidationError("quantity and unit must not be empty")
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValidationError("semantic quantity value must be finite")
    if not isinstance(citation, SourceCitation):
        raise ValidationError("semantic quantities require SourceCitation provenance")


@dataclass(frozen=True, slots=True)
class Target:
    quantity: str
    value: float
    unit: str
    citation: SourceCitation
    airspeed_kind: AirspeedKind | None = None
    notes: tuple[str, ...] = ()
    evidence: EvidenceKind = field(default=EvidenceKind.PROCEDURE_TARGET, init=False)

    def __post_init__(self) -> None:
        """Validate quantity metadata and normalize notes into an immutable tuple."""
        _validate_quantity(**{k: getattr(self, k) for k in ("quantity", "value", "unit", "citation")})
        object.__setattr__(self, "notes", tuple(self.notes))


@dataclass(frozen=True, slots=True)
class Limit:
    quantity: str
    value: float
    unit: str
    direction: LimitDirection
    citation: SourceCitation
    notes: tuple[str, ...] = ()
    evidence: EvidenceKind = field(default=EvidenceKind.PROCEDURE_LIMIT, init=False)

    def __post_init__(self) -> None:
        """
        Validate the limit fields and normalize notes into an immutable sequence.
        
        Raises:
            ValidationError: If the quantity data or limit direction is invalid.
        """
        _validate_quantity(**{k: getattr(self, k) for k in ("quantity", "value", "unit", "citation")})
        if not isinstance(self.direction, LimitDirection):
            raise ValidationError("limit direction must be LimitDirection")
        object.__setattr__(self, "notes", tuple(self.notes))


@dataclass(frozen=True, slots=True)
class Nominal:
    quantity: str
    value: float
    unit: str
    citation: SourceCitation
    adjustable: bool = True
    notes: tuple[str, ...] = ()
    evidence: EvidenceKind = field(default=EvidenceKind.PROCEDURE_NOMINAL, init=False)

    def __post_init__(self) -> None:
        """Validate quantity metadata and normalize notes into an immutable tuple."""
        _validate_quantity(**{k: getattr(self, k) for k in ("quantity", "value", "unit", "citation")})
        object.__setattr__(self, "notes", tuple(self.notes))


@dataclass(frozen=True, slots=True)
class InitialSetting:
    quantity: str
    value: float
    unit: str
    citation: SourceCitation
    approximate: bool = True
    notes: tuple[str, ...] = ()
    evidence: EvidenceKind = field(default=EvidenceKind.PROCEDURE_INITIAL_SETTING, init=False)

    def __post_init__(self) -> None:
        """Validate quantity metadata and normalize notes into an immutable tuple."""
        _validate_quantity(**{k: getattr(self, k) for k in ("quantity", "value", "unit", "citation")})
        object.__setattr__(self, "notes", tuple(self.notes))


@dataclass(frozen=True, slots=True)
class ControlRelationship:
    controlled_quantity: str
    control_input: ControlChannel
    description: str
    citation: SourceCitation
    evidence: EvidenceKind = field(
        default=EvidenceKind.PROCEDURE_CONTROL_RELATIONSHIP, init=False
    )

    def __post_init__(self) -> None:
        """
        Validate the control relationship fields and control channel.
        
        Raises:
            ValidationError: If the controlled quantity or description is empty, or
                if the control input is not a ControlChannel.
        """
        if not self.controlled_quantity.strip() or not self.description.strip():
            raise ValidationError("control relationship fields must not be empty")
        if not isinstance(self.control_input, ControlChannel):
            raise ValidationError("control_input must be a ControlChannel")


@dataclass(frozen=True, slots=True)
class PathConstraint:
    name: str
    description: str
    citation: SourceCitation
    evidence: EvidenceKind = field(default=EvidenceKind.PROCEDURE_PATH_CONSTRAINT, init=False)

    def __post_init__(self) -> None:
        """
        Validate that the path constraint name and description are nonempty.
        
        Raises:
            ValidationError: If either field is empty or contains only whitespace.
        """
        if not self.name.strip() or not self.description.strip():
            raise ValidationError("path constraint fields must not be empty")


@dataclass(frozen=True, slots=True)
class SafetyConstraint:
    quantity: str
    value: float
    unit: str
    direction: LimitDirection
    reference: str
    citation: SourceCitation
    evidence: EvidenceKind = field(default=EvidenceKind.PROCEDURE_LIMIT, init=False)

    def __post_init__(self) -> None:
        """
        Validate the safety constraint's quantity, reference, and direction fields.
        
        Raises:
            ValidationError: If a required field is invalid or the direction is not a
                LimitDirection member.
        """
        _validate_quantity(**{k: getattr(self, k) for k in ("quantity", "value", "unit", "citation")})
        if not self.reference.strip():
            raise ValidationError("safety-constraint reference must not be empty")
        if not isinstance(self.direction, LimitDirection):
            raise ValidationError("safety-constraint direction must be LimitDirection")


@dataclass(frozen=True, slots=True)
class TerminationSpec:
    name: str
    description: str
    citation: SourceCitation | None
    source_defined: bool
    implemented: bool
    quantity: str | None = None
    value: float | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        """Validate termination criteria fields and their optional quantity data.
        
        Raises:
            ValidationError: If required text is empty, the value is non-finite, or
                quantity, value, and unit are not supplied together.
        """
        if not self.name.strip() or not self.description.strip():
            raise ValidationError("termination-spec fields must not be empty")
        if self.value is not None and (isinstance(self.value, bool) or not math.isfinite(self.value)):
            raise ValidationError("termination value must be finite when supplied")
        if (self.quantity is None) != (self.value is None) or (self.value is None) != (self.unit is None):
            raise ValidationError("termination quantity, value and unit must be supplied together")


@dataclass(frozen=True, slots=True)
class ManeuverPhase:
    name: str
    entry_conditions: tuple[str, ...] = ()
    targets: tuple[Target, ...] = ()
    limits: tuple[Limit, ...] = ()
    nominals: tuple[Nominal, ...] = ()
    initial_settings: tuple[InitialSetting, ...] = ()
    control_relationships: tuple[ControlRelationship, ...] = ()
    path_constraints: tuple[PathConstraint, ...] = ()
    exit_conditions: tuple[TerminationSpec, ...] = ()
    gaps: tuple[ModelGap, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("phase name must not be empty")
        for field_name in (
            "entry_conditions",
            "targets",
            "limits",
            "nominals",
            "initial_settings",
            "control_relationships",
            "path_constraints",
            "exit_conditions",
            "gaps",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


@dataclass(frozen=True, slots=True)
class ManeuverSpec:
    name: str
    objective: str
    source: SourceCitation
    phases: tuple[ManeuverPhase, ...]
    safety_constraints: tuple[SafetyConstraint, ...] = ()
    termination_conditions: tuple[TerminationSpec, ...] = ()
    gaps: tuple[ModelGap, ...] = ()

    def __post_init__(self) -> None:
        """
        Validate the maneuver specification and normalize its collection fields.
        
        Raises:
            ValidationError: If the maneuver name or objective is empty, no phases
                are provided, or phase names are duplicated.
        """
        if not self.name.strip() or not self.objective.strip():
            raise ValidationError("maneuver name and objective must not be empty")
        object.__setattr__(self, "phases", tuple(self.phases))
        object.__setattr__(self, "safety_constraints", tuple(self.safety_constraints))
        object.__setattr__(self, "termination_conditions", tuple(self.termination_conditions))
        object.__setattr__(self, "gaps", tuple(self.gaps))
        if not self.phases:
            raise ValidationError("ManeuverSpec requires at least one phase")
        phase_names = [phase.name for phase in self.phases]
        if len(phase_names) != len(set(phase_names)):
            raise ValidationError("ManeuverSpec phase names must be unique")

    def phase(self, name: str) -> ManeuverPhase:
        """Retrieve a maneuver phase by name.
        
        Parameters:
            name (str): Name of the phase to retrieve.
        
        Returns:
            ManeuverPhase: The phase with the matching name.
        
        Raises:
            KeyError: If no phase has the specified name.
        """
        for phase in self.phases:
            if phase.name == name:
                return phase
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class AdvisoryValue:
    quantity: str
    value: float | str
    unit: str | None

    def __post_init__(self) -> None:
        """
        Validate the advisory value's quantity, numeric value, and optional unit.
        
        Raises:
            ValidationError: If the quantity or supplied unit is empty, or if a
                numeric value is not finite.
        """
        if not self.quantity.strip():
            raise ValidationError("advisory quantity must not be empty")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValidationError("numeric advisory value must be finite")
        if self.unit is not None and not self.unit.strip():
            raise ValidationError("advisory unit must not be empty when supplied")


@dataclass(frozen=True, slots=True)
class AdvisoryReference:
    maneuver_name: str
    phase_name: str | None
    values: tuple[AdvisoryValue, ...]
    citation: SourceCitation
    evidence: EvidenceKind = field(default=EvidenceKind.ADVISORY_REFERENCE, init=False)

    def __post_init__(self) -> None:
        """
        Normalize advisory values to an immutable tuple and validate the maneuver name and values.
        
        Raises:
            ValidationError: If the maneuver name is empty or no advisory values are provided.
        """
        object.__setattr__(self, "values", tuple(self.values))
        if not self.maneuver_name.strip() or not self.values:
            raise ValidationError("AdvisoryReference requires a maneuver name and values")


@dataclass(frozen=True, slots=True)
class ManeuverPackage:
    """Pairs authoritative narrative semantics with separately held references."""

    spec: ManeuverSpec
    advisory_references: tuple[AdvisoryReference, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ManeuverSpec):
            raise ValidationError("ManeuverPackage spec must be a ManeuverSpec")
        object.__setattr__(self, "advisory_references", tuple(self.advisory_references))
        if any(not isinstance(item, AdvisoryReference) for item in self.advisory_references):
            raise ValidationError("advisory_references must contain AdvisoryReference values")
