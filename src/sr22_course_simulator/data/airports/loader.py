"""Load the supplied canonical AIP records without duplicating source values."""

import json
from importlib.resources import files

from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.airport import AirportSpec, RunwaySpec
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.provenance import SourceCitation


def load_airport(icao: str) -> AirportSpec:
    """Load a bundled airport; missing source fields are explicit model gaps.

    The current canonical source domain is one physical runway per airport,
    with two reciprocal directions. No geometry or operational values are
    inferred from ARP, magnetic variation, or local/IFR restrictions.
    """
    if (
        not isinstance(icao, str)
        or len(icao) != 4
        or not icao.isascii()
        or not icao.isalnum()
    ):
        raise ValidationError(
            "airport ICAO must contain four ASCII alphanumeric characters"
        )
    icao = icao.upper()
    resource = files(__package__).joinpath("canonical", f"{icao}.json")
    try:
        record = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(
            f"{icao}: model gap: no bundled canonical AIP source"
        ) from exc

    def citation(section: str) -> SourceCitation:
        document = record["source_document"]
        location = document["section_sources"][section]
        return SourceCitation(
            document_title=f"AIP Japan {icao} AD 2 ({document['file_name']})",
            effective_date=location["effective_date"],
            section=f"{icao} {section.upper().replace('_', ' ', 1).replace('_', '.')}",
            page=location["aip_page"],
            extraction_method="supplied canonical AIP JSON transcription",
            transformations=(
                "reciprocal runway retains physical thresholds in reverse order",
            ),
            notes=(
                f"source PDF page: {location['pdf_page']}",
                f"source SHA-256: {document['sha256']}",
                "raw PDF is not committed in this repository",
            ),
        )

    try:
        if record["icao"] != icao:
            raise ValidationError(f"{icao}: canonical airport identity mismatch")
        aerodrome = record["aerodrome"]
        runway_records = record["runways"]
        if not isinstance(runway_records, dict):
            raise ValidationError(
                f"{icao}: model gap: canonical runways must be a mapping of runway designators"
            )
        directions = tuple(runway_records.values())
        if len(directions) != 2:
            raise ValidationError(
                f"{icao}: model gap: loader requires exactly two reciprocal directions; "
                "multiple physical runways require an explicit threshold-pair relationship"
            )
        runways = []
        for runway, reciprocal in (directions, directions[::-1]):
            threshold = runway["threshold"]
            opposite = reciprocal["threshold"]
            bearing_difference = (
                runway["true_bearing_deg"] - reciprocal["true_bearing_deg"]
            ) % 360
            if abs(bearing_difference - 180) > 0.01:
                raise ValidationError(
                    f"{icao}: source runway bearings are not reciprocal"
                )
            runways.append(
                RunwaySpec(
                    designation=runway["designator"],
                    true_bearing_deg=runway["true_bearing_deg"],
                    threshold_a=GeoPosition(
                        threshold["latitude_deg"], threshold["longitude_deg"]
                    ),
                    threshold_b=GeoPosition(
                        opposite["latitude_deg"], opposite["longitude_deg"]
                    ),
                    threshold_elevation_a_ft=threshold["elevation_ft"],
                    threshold_elevation_b_ft=opposite["elevation_ft"],
                    declared_length_m=runway["dimensions"]["length_m"],
                    width_m=runway["dimensions"]["width_m"],
                    source=citation("ad_2_12"),
                )
            )
        variation = aerodrome["magnetic_variation"]
        return AirportSpec(
            icao=icao,
            name=record["name_en"],
            reference_point=GeoPosition(
                aerodrome["arp"]["latitude_deg"], aerodrome["arp"]["longitude_deg"]
            ),
            elevation_ft=aerodrome["elevation_ft"],
            magnetic_variation_deg=variation["variation_deg_signed"],
            magnetic_variation_epoch_year=variation["epoch_year"],
            annual_change_deg_per_year=variation["annual_change_deg_per_year_signed"],
            source=citation("ad_2_2"),
            runways=tuple(runways),
        )
    except (KeyError, TypeError) as exc:
        raise ValidationError(
            f"{icao}: model gap: missing/invalid canonical airport source field: {exc}"
        ) from exc
