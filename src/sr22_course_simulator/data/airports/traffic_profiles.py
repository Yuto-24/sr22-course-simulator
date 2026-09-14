"""Issue #9 operational profiles; airport geometry stays in canonical JSON."""

from __future__ import annotations

from dataclasses import dataclass
import math

from sr22_course_simulator.data.airports import load_airport
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.path import DescentStart, PatternSide, TrafficPatternSpec
from sr22_course_simulator.provenance import SourceCitation

ISSUE_SOURCE = "https://github.com/Yuto-24/sr22-course-simulator/issues/9"
TRAINING_SOURCE = "学生訓練実施要領 改正19"
GENERIC_ALTITUDE_RULE = (
    "generic_field_plus_1000: nearest 100 ft to Field Elevation + 1000 ft; "
    "exact 50 ft rounds upward. 学生訓練実施要領 改正19 第4章 通常Departure "
    "AGL+1000 ft; 第3章 Approach briefing 釧路311 ft -> 1300 ft."
)


@dataclass(frozen=True, slots=True)
class _Profile:
    runway: str
    side: PatternSide
    altitude_ft: float | None = None  # None selects the sourced generic rule.
    descent: DescentStart = DescentStart.BASE_TURN_START
    preferred: bool = False


L, R = PatternSide.LEFT, PatternSide.RIGHT
ABEAM = DescentStart.ABEAM_THRESHOLD
BASE_END = DescentStart.BASE_TURN_END

# Operational values transcribed from Issue #9, not airport geometry/AIP copies.
_PROFILES = {
    "RJFS": (
        _Profile("11", L, 1000),
        _Profile("11", R, 1000, preferred=True),
        _Profile("29", L, 1000, preferred=True),
        _Profile("29", R, 1000),
    ),
    "RJFO": (
        _Profile("01", L, 1300, ABEAM),
        _Profile("01", R, preferred=True),
        _Profile("19", L, preferred=True),
        _Profile("19", R, 1300, ABEAM),
    ),
    "RJFK": (
        _Profile("16", L),
        _Profile("16", R),
        _Profile("34", L),
        _Profile("34", R),
    ),
    "RJFT": (
        _Profile("07", L, 1400, BASE_END),
        _Profile("07", R, 1700),
        _Profile("25", L, 1700),
        _Profile("25", R, 1400, BASE_END),
    ),
    "RJFG": (
        _Profile("13", L, 1800, preferred=True),
        _Profile("13", R, 1800),
        _Profile("31", L, 1800),
        _Profile("31", R, 1800, preferred=True),
    ),
    "RJFU": (
        _Profile("14", L),
        _Profile("14", R),
        _Profile("32", L),
        _Profile("32", R),
    ),
    "RJFC": (
        _Profile("14", L),
        _Profile("14", R),
        _Profile("32", L),
        _Profile("32", R),
    ),
}
RJF_AIRPORTS = tuple(_PROFILES)

_LOCAL_NOTES = {
    "RJFS": "SR22 1000 ft; North/South width 1.5 NM; normally south traffic.",
    "RJFO": "West Downwind 1300 ft; terrain 810 ft near runway abeam; descend from Abeam Threshold. East/sea preferred under local sea-flight rule; both sides retained.",
    "RJFK": "RWY34 Downwind / RWY16 Right Base terrain and traffic cautions; no explicit local SR22 altitude identified in Issue #9; no preferred side assigned.",
    "RJFT": "North 1400 ft, descent after Base Turn end; AIP AD2.23 single-engine nominal 1400 ft. South local operation 1700 ft explicitly overrides that nominal altitude.",
    "RJFG": "Normally north Downwind; local training statement specifies field + 1000 as 1800 ft.",
    "RJFU": "Southwest Downwind-entry cautions; no explicit local altitude identified in Issue #9. Island/sea-flight context does not select LEFT/RIGHT preference.",
    "RJFC": "No VFR pattern side/altitude restriction supplied in AD2.20; IFR Circling EAST only is not a VFR Traffic Pattern restriction.",
}


def generic_pattern_altitude_ft(field_elevation_ft: float) -> float:
    """Resolve the Issue #9 field + 1000 rule with explicit half-up rounding."""
    if isinstance(field_elevation_ft, bool) or not math.isfinite(field_elevation_ft):
        raise ValidationError("field_elevation_ft must be finite")
    return math.floor((field_elevation_ft + 1000.0 + 50.0) / 100.0) * 100.0


def rjf_traffic_pattern_specs(
    icao: str,
    *,
    make_circle_before_downwind: bool = True,
    make_270_before_downwind: bool = True,
    make_circle_middle_downwind: bool = True,
    make_circle_before_base: bool = False,
    make_270_before_base: bool = True,
) -> tuple[TrafficPatternSpec, ...]:
    """Resolve all four profiles, including non-preferred sides, from Issue #9.

    Geometry and source dates are loaded from bundled airport JSON. The five
    switches keep the RJFM defaults and are independently validated by the spec.
    """
    if not isinstance(icao, str) or icao.strip().upper() not in _PROFILES:
        raise ValidationError(
            f"model gap: {icao!r} has no Issue #9 operational profile; "
            "local altitude/descent/preference or an applicable generic rule is required"
        )
    icao = icao.strip().upper()
    airport = load_airport(icao)
    specs = []
    for profile in _PROFILES[icao]:
        runway = airport.runway(profile.runway)
        generic = profile.altitude_ft is None
        altitude = (
            generic_pattern_altitude_ft(airport.elevation_ft)
            if generic
            else profile.altitude_ft
        )
        altitude_note = (
            f"{GENERIC_ALTITUDE_RULE} canonical field {airport.elevation_ft:g} ft -> {altitude:g} ft MSL."
            if generic
            else f"local_explicit: {altitude:g} ft MSL, operational profile from Issue #9."
        )
        source = SourceCitation(
            document_title=(
                "航空大学校所属航空機の他空港利用に関する調整事項[2026.4.1].pdf"
                if icao == "RJFS"
                else TRAINING_SOURCE
            ),
            revision=None if icao == "RJFS" else "改正19",
            effective_date="2026-04-01" if icao == "RJFS" else None,
            section=f"Issue #9 {icao} airport profile; common geometry and generic altitude rule",
            extraction_method=f"task-provided source transcription: {ISSUE_SOURCE}",
            transformations=(
                "Canonical threshold midpoint and True Bearing define geometry; ARP/magnetic variation are reference-only.",
                "Issue #9 geometry assumptions: 110 KTAS, 30/22/22/25 deg turns, Circle/270 22 deg, roll 10 deg/s, Final 3 deg, axes 1.5/1.5 NM.",
                "Existing independent-component geometry and continuous altitude interpolation; not a flight-dynamics or terrain-clearance model.",
            ),
            notes=(
                altitude_note,
                _LOCAL_NOTES[icao],
                "procedure_target: operational pattern altitude; assumed: task-selected ReferencePath dimensions and turn settings.",
                f"Airport geometry: {airport.source.document_title}; effective {airport.source.effective_date}; {airport.source.section}.",
                f"Runway geometry: {runway.source.document_title}; effective {runway.source.effective_date}; {runway.source.section}.",
                "Primary operational PDFs were not independently re-transcribed for this dataset; provenance is the supplied Issue #9 transcription.",
            ),
        )
        specs.append(
            TrafficPatternSpec(
                airport=airport,
                runway=runway,
                side=profile.side,
                altitude_ft=altitude,
                downwind_offset_nm=1.5,
                crosswind_base_extension_nm=1.5,
                source=source,
                descent_start=profile.descent,
                preferred=profile.preferred,
                notes=(altitude_note, _LOCAL_NOTES[icao]),
                make_circle_before_downwind=make_circle_before_downwind,
                make_270_before_downwind=make_270_before_downwind,
                make_circle_middle_downwind=make_circle_middle_downwind,
                make_circle_before_base=make_circle_before_base,
                make_270_before_base=make_270_before_base,
            )
        )
    return tuple(specs)
