"""Verified Chapter 5 Spiral Descent narrative transcription.

The narrative pages and the chapter-end Reference Data page are encoded through
separate object types.  Gear instructions are retained in provenance notes but
are not introduced into the fixed-gear SR22 core API.
"""

from __future__ import annotations

from sr22_course_simulator.aircraft.state import AirspeedKind
from sr22_course_simulator.maneuver.spec import (
    AdvisoryReference,
    AdvisoryValue,
    ControlChannel,
    ControlRelationship,
    InitialSetting,
    Limit,
    LimitDirection,
    ManeuverPackage,
    ManeuverPhase,
    ManeuverSpec,
    Nominal,
    PathConstraint,
    SafetyConstraint,
    Target,
    TerminationSpec,
)
from sr22_course_simulator.provenance import GapKind, ModelGap, SourceCitation


def _narrative_citation() -> SourceCitation:
    """Identify the primary narrative source for the Spiral Descent maneuver specification.
    
    Returns:
    	SourceCitation: Citation for the training-procedure document and section from which the maneuver narrative was transcribed.
    """
    return SourceCitation(
        document_title="航空大学校 学生訓練実施要領 単発事業用課程",
        revision="改正19",
        effective_date="2026-06-24",
        chapter="5",
        section="Spiral Descent",
        page="5-(34) to 5-(35) (PDF pages 157-158)",
        extraction_method="Manual semantic transcription from the primary PDF text layer",
        notes=(
            "Section pages dated 2020-12-16.",
            "Source includes retractable-Gear actions; retained here only as provenance because the project SR22 target has fixed gear.",
        ),
    )


def _minimum_altitude_citation() -> SourceCitation:
    """
    Provide the source citation for the 2,000-ft AGL minimum training-height requirement.
    
    Returns:
        SourceCitation: Citation for the applicable training-height requirement.
    """
    return SourceCitation(
        document_title="航空大学校 学生訓練実施要領 単発事業用課程",
        revision="改正19",
        effective_date="2026-06-24",
        chapter="5",
        section="5-1 General / maneuver minimum training height",
        page="5-(1) (PDF page 124)",
        extraction_method="Manual semantic transcription from the primary PDF text layer",
        notes=("Page dated 2026-03-02.",),
    )


def _advisory_citation() -> SourceCitation:
    """
    Provide the source citation for the Spiral Descent advisory reference data.
    
    Returns:
        SourceCitation: Citation for the Spiral Descent row in section 5-12
            of the specified training document.
    """
    return SourceCitation(
        document_title="航空大学校 学生訓練実施要領 単発事業用課程",
        revision="改正19",
        effective_date="2026-06-24",
        chapter="5",
        section="5-12 Reference Data",
        page="5-(49) (PDF page 172)",
        table="Spiral Descent row",
        extraction_method="Manual transcription from the primary PDF text layer",
        notes=(
            "Page dated 2023-07-06.",
            "The source explicitly says Pitch/Power are approximate and vary with weight, temperature and altitude.",
        ),
    )


def spiral_descent_package() -> ManeuverPackage:
    """
    Build the verified Spiral Descent maneuver specification with its advisory reference data.
    
    Returns:
        ManeuverPackage: A maneuver package containing entry, execution, and recovery phases, a
        2,000-foot AGL minimum training-height constraint, 720-degree completion condition,
        documented modeling gaps, and advisory values for airspeed, pitch, power, bank, gear,
        and flaps.
    """

    source = _narrative_citation()
    airspeed_kind_gap = ModelGap(
        kind=GapKind.SOURCE_NOT_STATED,
        quantity="110 kt airspeed type",
        description="The narrative prints 110 kt without establishing IAS, CAS, or TAS in the encoded passage.",
        citation=source,
    )
    recovery_gap = ModelGap(
        kind=GapKind.NOT_IMPLEMENTED,
        quantity="recovery guidance",
        description="The recovery narrative is encoded, but the current guided integrator stops at 720 degrees or the minimum-height boundary.",
        citation=source,
    )
    descent_model_gap = ModelGap(
        kind=GapKind.SOURCE_DATA_MISSING,
        quantity="Pitch/PWR/Bank to descent performance",
        description="The applicable POH Chapter 5 contains no Spiral Descent/descent response table for this operating region.",
        citation=source,
    )
    nonmodeled_procedure_gap = ModelGap(
        kind=GapKind.NOT_IMPLEMENTED,
        quantity="Gear and Mixture procedure actions",
        description="Source Gear actions are inapplicable to the fixed-gear target; the 5,000-ft Mixture action is preserved as text but is not a core FlightInput.",
        citation=source,
    )

    entry = ManeuverPhase(
        name="entry",
        entry_conditions=(
            "Judge wind from surface indications, using PFD wind aloft as reference.",
            "Clear the airspace, set a Pylon, and normally choose a heading permitting tailwind entry.",
        ),
        targets=(
            Target(
                quantity="airspeed_at_pylon_abeam",
                value=110.0,
                unit="kt",
                airspeed_kind=AirspeedKind.UNSPECIFIED,
                citation=source,
                notes=("Airspeed kind awaits primary-source verification.",),
            ),
        ),
        initial_settings=(
            InitialSetting(
                quantity="power",
                value=10.0,
                unit="percent",
                approximate=True,
                citation=source,
                notes=("Entry setting only; not an established-maneuver fixed command.",),
            ),
        ),
        path_constraints=(
            PathConstraint(
                name="pylon_abeam_entry",
                description="Lead the entry so the airspeed target is achieved at pylon abeam.",
                citation=source,
            ),
        ),
        gaps=(airspeed_kind_gap, nonmodeled_procedure_gap),
    )

    execution = ManeuverPhase(
        name="execution",
        entry_conditions=(
            "At Pylon abeam, begin the turn and establish the 110-kt descent attitude.",
        ),
        targets=(
            Target(
                quantity="airspeed",
                value=110.0,
                unit="kt",
                airspeed_kind=AirspeedKind.UNSPECIFIED,
                citation=source,
                notes=("Maintain with Pitch; airspeed type is not identified in this passage.",),
            ),
        ),
        initial_settings=(
            InitialSetting(
                quantity="pitch",
                value=-1.0,
                unit="deg",
                approximate=True,
                citation=source,
                notes=("Narrative reference for establishing descent attitude; not a fixed command.",),
            ),
        ),
        nominals=(
            Nominal(
                quantity="bank",
                value=45.0,
                unit="deg",
                adjustable=True,
                citation=source,
                notes=("Nominal value; wind/path guidance may vary Bank within the limit.",),
            ),
        ),
        limits=(
            Limit(
                quantity="absolute_bank",
                value=55.0,
                unit="deg",
                direction=LimitDirection.MAXIMUM,
                citation=source,
            ),
        ),
        control_relationships=(
            ControlRelationship(
                controlled_quantity="pylon / desired ground-path relationship",
                control_input=ControlChannel.BANK,
                description="Adjust Bank as required by wind and path error while respecting maximum Bank.",
                citation=source,
            ),
            ControlRelationship(
                controlled_quantity="target airspeed",
                control_input=ControlChannel.PITCH,
                description="Use Pitch as a guidance control variable for target airspeed; no fixed reference Pitch is imposed.",
                citation=source,
            ),
        ),
        path_constraints=(
            PathConstraint(
                name="pylon_relationship",
                description="Maintain the source-defined relationship to the selected pylon while judging wind.",
                citation=source,
            ),
        ),
        exit_conditions=(
            TerminationSpec(
                name="complete_720_degree_turn",
                description="Roll out and level off after 720 degrees of turn.",
                citation=source,
                source_defined=True,
                implemented=True,
                quantity="accumulated_turn",
                value=720.0,
                unit="deg",
            ),
        ),
        gaps=(nonmodeled_procedure_gap, descent_model_gap),
    )

    recovery = ManeuverPhase(
        name="recovery",
        entry_conditions=(
            "Roll out and level off after 720 degrees; if 2,000 ft AGL is reached first, keep altitude and continue to the prescribed heading before rollout.",
            "Keep final altitude and heading during recovery.",
        ),
        initial_settings=(
            InitialSetting(
                quantity="power",
                value=100.0,
                unit="percent",
                approximate=False,
                citation=source,
                notes=("Apply MAX Power smoothly; source cautions against engine hesitation.",),
            ),
        ),
        exit_conditions=(
            TerminationSpec(
                name="after_complete",
                description="Perform Cruise Procedure and call maneuver complete.",
                citation=source,
                source_defined=True,
                implemented=False,
            ),
        ),
        gaps=(recovery_gap,),
    )
    completion = TerminationSpec(
        name="complete_720_degree_turn",
        description="After 720 degrees, roll out and level off; then execute Recovery and After Complete.",
        citation=source,
        source_defined=True,
        implemented=True,
        quantity="accumulated_turn",
        value=720.0,
        unit="deg",
    )
    minimum_altitude = SafetyConstraint(
        quantity="minimum_training_height",
        value=2000.0,
        unit="ft",
        direction=LimitDirection.MINIMUM,
        reference="AGL",
        citation=_minimum_altitude_citation(),
    )
    spec = ManeuverSpec(
        name="Spiral Descent",
        objective="Execute a descending pylon-referenced maneuver while judging wind and maintaining source-defined targets and limits.",
        source=source,
        phases=(entry, execution, recovery),
        safety_constraints=(minimum_altitude,),
        termination_conditions=(completion,),
        gaps=(airspeed_kind_gap, descent_model_gap, recovery_gap, nonmodeled_procedure_gap),
    )
    advisory = AdvisoryReference(
        maneuver_name="Spiral Descent",
        phase_name=None,
        values=(
            AdvisoryValue("airspeed", 110.0, "kt"),
            AdvisoryValue("pitch", -1.0, "deg"),
            AdvisoryValue("power", 10.0, "percent"),
            AdvisoryValue("bank", 45.0, "deg"),
            AdvisoryValue("gear", "DOWN", None),
            AdvisoryValue("flaps", "UP", None),
        ),
        citation=_advisory_citation(),
    )
    return ManeuverPackage(spec=spec, advisory_references=(advisory,))
