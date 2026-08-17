"""RJFM master data transcribed from the task-provided AIP values."""

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.airport import AirportSpec, RunwaySpec, parse_aip_dms
from sr22_course_simulator.provenance import SourceCitation


RJFM_AD_2_2_SOURCE = SourceCitation(
    document_title="AIP Japan RJFM AD 2 (RJFM__20260301.pdf)",
    effective_date="2026-03-01",
    section="RJFM AD 2.2",
    extraction_method="task-provided transcription",
    transformations=(
        "compact DMS coordinates converted deterministically to decimal degrees",
        "west magnetic variation and annual change encoded as negative degrees",
    ),
    notes=("raw PDF is not committed in this repository",),
)

RJFM_AD_2_12_SOURCE = SourceCitation(
    document_title="AIP Japan RJFM AD 2 (RJFM__20260301.pdf)",
    effective_date="2026-03-01",
    section="RJFM AD 2.12",
    extraction_method="task-provided transcription",
    transformations=(
        "compact DMS coordinates converted deterministically to decimal degrees",
        "reciprocal landing directions retain the same physical thresholds in reverse order",
    ),
    notes=("raw PDF is not committed in this repository",),
)


_THRESHOLD_09 = GeoPosition(
    parse_aip_dms("315234.26N"),
    parse_aip_dms("1312607.02E"),
)
_THRESHOLD_27 = GeoPosition(
    parse_aip_dms("315241.06N"),
    parse_aip_dms("1312741.80E"),
)

_RUNWAY_09 = RunwaySpec(
    designation="09",
    true_bearing_deg=85.18,
    threshold_a=_THRESHOLD_09,
    threshold_b=_THRESHOLD_27,
    threshold_elevation_a_ft=15.0,
    threshold_elevation_b_ft=20.7,
    declared_length_m=2_500.0,
    width_m=45.0,
    source=RJFM_AD_2_12_SOURCE,
)

_RUNWAY_27 = RunwaySpec(
    designation="27",
    true_bearing_deg=265.18,
    threshold_a=_THRESHOLD_27,
    threshold_b=_THRESHOLD_09,
    threshold_elevation_a_ft=20.7,
    threshold_elevation_b_ft=15.0,
    declared_length_m=2_500.0,
    width_m=45.0,
    source=RJFM_AD_2_12_SOURCE,
)

RJFM = AirportSpec(
    icao="RJFM",
    name="Miyazaki Airport",
    reference_point=GeoPosition(
        parse_aip_dms("315238N"),
        parse_aip_dms("1312655E"),
    ),
    elevation_ft=19.0,
    magnetic_variation_deg=-7.0,
    magnetic_variation_epoch_year=2020.0,
    annual_change_deg_per_year=-(5.0 / 60.0),
    source=RJFM_AD_2_2_SOURCE,
    runways=(_RUNWAY_09, _RUNWAY_27),
)
