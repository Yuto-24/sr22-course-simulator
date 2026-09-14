import json
import tempfile
import unittest
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from sr22_course_simulator.airport import parse_aip_dms
from sr22_course_simulator.data.airports import RJFM, load_airport
from sr22_course_simulator.errors import ValidationError

AIRPORTS = ("RJFC", "RJFG", "RJFK", "RJFM", "RJFO", "RJFS", "RJFT", "RJFU")
CANONICAL = files("sr22_course_simulator.data.airports").joinpath("canonical")


class AirportLoaderTests(unittest.TestCase):
    def test_all_eight_airports_reproduce_canonical_source_values(self):
        for icao in AIRPORTS:
            with self.subTest(icao=icao):
                data = json.loads(CANONICAL.joinpath(f"{icao}.json").read_text())
                airport = load_airport(icao)
                self.assertEqual(airport.icao, icao)
                self.assertEqual(
                    airport.elevation_ft, data["aerodrome"]["elevation_ft"]
                )
                variation = data["aerodrome"]["magnetic_variation"]
                self.assertEqual(
                    airport.magnetic_variation_deg, variation["variation_deg_signed"]
                )
                self.assertEqual(
                    airport.magnetic_variation_epoch_year, variation["epoch_year"]
                )
                self.assertEqual(
                    airport.annual_change_deg_per_year,
                    variation["annual_change_deg_per_year_signed"],
                )
                self.assertEqual(
                    airport.reference_point.latitude_deg,
                    data["aerodrome"]["arp"]["latitude_deg"],
                )
                self.assertEqual(
                    airport.reference_point.longitude_deg,
                    data["aerodrome"]["arp"]["longitude_deg"],
                )
                self.assertEqual(len(airport.runways), 2)
                for runway in airport.runways:
                    source = data["runways"][runway.designation]
                    self.assertEqual(
                        runway.true_bearing_deg, source["true_bearing_deg"]
                    )
                    self.assertEqual(
                        runway.declared_length_m, source["dimensions"]["length_m"]
                    )
                    self.assertEqual(runway.width_m, source["dimensions"]["width_m"])
                    threshold = source["threshold"]
                    self.assertEqual(
                        runway.threshold_elevation_a_ft, threshold["elevation_ft"]
                    )
                    self.assertEqual(
                        runway.threshold_a.latitude_deg, threshold["latitude_deg"]
                    )
                    self.assertEqual(
                        runway.threshold_a.longitude_deg, threshold["longitude_deg"]
                    )
                    self.assertAlmostEqual(
                        runway.threshold_a.latitude_deg,
                        parse_aip_dms(threshold["latitude_raw"]),
                        places=12,
                    )
                    self.assertAlmostEqual(
                        runway.threshold_a.longitude_deg,
                        parse_aip_dms(threshold["longitude_raw"]),
                        places=12,
                    )
                a, b = airport.runways
                self.assertEqual(a.threshold_a, b.threshold_b)
                self.assertEqual(a.threshold_b, b.threshold_a)
                self.assertEqual(a.threshold_elevation_b_ft, b.threshold_elevation_a_ft)
                self.assertEqual(a.center_point, b.center_point)
                self.assertEqual(
                    a.center_point.latitude_deg,
                    (a.threshold_a.latitude_deg + a.threshold_b.latitude_deg) / 2,
                )

    def test_section_specific_provenance_survives_loading(self):
        for icao in AIRPORTS:
            data = json.loads(CANONICAL.joinpath(f"{icao}.json").read_text())
            airport = load_airport(icao)
            document = data["source_document"]
            for source, section in (
                (airport.source, "ad_2_2"),
                (airport.runways[0].source, "ad_2_12"),
            ):
                self.assertIn(document["file_name"], source.document_title)
                self.assertEqual(
                    source.effective_date,
                    document["section_sources"][section]["effective_date"],
                )
                self.assertEqual(
                    source.page, document["section_sources"][section]["aip_page"]
                )
                self.assertEqual(
                    source.section, f"{icao} AD 2.{2 if section == 'ad_2_2' else 12}"
                )
                self.assertIn(document["sha256"], " ".join(source.notes))
        self.assertEqual(RJFM.source.effective_date, "2026-03-01")
        self.assertEqual(RJFM.runway("09").source.effective_date, "2025-05-15")

    def test_runway_transformations_are_not_attached_to_aerodrome_sources(self):
        for icao in AIRPORTS:
            with self.subTest(icao=icao):
                airport = load_airport(icao)
                self.assertEqual(airport.source.transformations, ())
                for runway in airport.runways:
                    self.assertEqual(
                        runway.source.transformations,
                        (
                            "reciprocal runway retains physical thresholds in reverse order",
                        ),
                    )

    def test_invalid_coordinate_value_reports_contextual_model_gap(self):
        for field in ("latitude_deg", "longitude_deg"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                data = json.loads(CANONICAL.joinpath("RJFM.json").read_text())
                data["runways"]["09"]["threshold"][field] = "not-a-coordinate"
                root = Path(directory)
                (root / "canonical").mkdir()
                (root / "canonical/RJFM.json").write_text(json.dumps(data))
                with (
                    patch(
                        "sr22_course_simulator.data.airports.loader.files",
                        return_value=root,
                    ),
                    self.assertRaisesRegex(
                        ValidationError, "RJFM.*model gap.*not-a-coordinate"
                    ) as caught,
                ):
                    load_airport("RJFM")
                self.assertIs(type(caught.exception.__cause__), ValueError)

    def test_existing_domain_validation_error_is_preserved(self):
        error = ValidationError("specific source geometry constraint")
        with (
            patch(
                "sr22_course_simulator.data.airports.loader.RunwaySpec",
                side_effect=error,
            ),
            self.assertRaises(ValidationError) as caught,
        ):
            load_airport("RJFM")
        self.assertIs(caught.exception, error)
        self.assertIsNone(caught.exception.__cause__)

    def test_rjfm_numeric_parity_with_original_python_transcription(self):
        # These are the pre-loader rjfm.py source values, not generated geometry.
        self.assertEqual(RJFM.reference_point.latitude_deg, parse_aip_dms("315238N"))
        self.assertEqual(RJFM.reference_point.longitude_deg, parse_aip_dms("1312655E"))
        self.assertEqual(
            (
                RJFM.elevation_ft,
                RJFM.magnetic_variation_deg,
                RJFM.magnetic_variation_epoch_year,
                RJFM.annual_change_deg_per_year,
            ),
            (19.0, -7.0, 2020.0, -5 / 60),
        )
        for runway, expected in zip(
            RJFM.runways,
            (
                ("09", 85.18, "315234.26N", "1312607.02E", 15.0, 20.7),
                ("27", 265.18, "315241.06N", "1312741.80E", 20.7, 15.0),
            ),
        ):
            designation, bearing, lat, lon, alt_a, alt_b = expected
            self.assertEqual(
                (
                    runway.designation,
                    runway.true_bearing_deg,
                    runway.threshold_a.latitude_deg,
                    runway.threshold_a.longitude_deg,
                    runway.threshold_elevation_a_ft,
                    runway.threshold_elevation_b_ft,
                    runway.declared_length_m,
                    runway.width_m,
                ),
                (
                    designation,
                    bearing,
                    parse_aip_dms(lat),
                    parse_aip_dms(lon),
                    alt_a,
                    alt_b,
                    2500.0,
                    45.0,
                ),
            )

    def test_missing_airport_and_invalid_identity_report_gap(self):
        with self.assertRaisesRegex(
            ValidationError, "RJFE.*no bundled canonical AIP source"
        ):
            load_airport("RJFE")
        for invalid in ("../x", "RJFM.json", None, 1234):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                load_airport(invalid)

    def test_missing_geometry_field_is_not_filled_from_other_data(self):
        data = json.loads(CANONICAL.joinpath("RJFM.json").read_text())
        del data["runways"]["09"]["threshold"]["elevation_ft"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "canonical").mkdir()
            (root / "canonical/RJFM.json").write_text(json.dumps(data))
            with patch(
                "sr22_course_simulator.data.airports.loader.files", return_value=root
            ):
                with self.assertRaisesRegex(
                    ValidationError, "RJFM.*model gap.*elevation_ft"
                ):
                    load_airport("RJFM")

    def test_malformed_runways_container_reports_contextual_model_gap(self):
        data = json.loads(CANONICAL.joinpath("RJFM.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "canonical").mkdir()
            for malformed in ([], None, "09/27", 2):
                with self.subTest(runways=malformed):
                    data["runways"] = malformed
                    (root / "canonical/RJFM.json").write_text(json.dumps(data))
                    with patch(
                        "sr22_course_simulator.data.airports.loader.files",
                        return_value=root,
                    ):
                        with self.assertRaisesRegex(
                            ValidationError, "RJFM.*model gap.*runways.*mapping"
                        ):
                            load_airport("RJFM")

    def test_bearing_sanity_tolerance_does_not_change_source_geometry(self):
        runway = load_airport("RJFO").runway("01")
        self.assertEqual(runway.true_bearing_deg, 0.0)
        self.assertGreater(
            runway.threshold_b.longitude_deg, runway.threshold_a.longitude_deg
        )
        with self.assertRaisesRegex(ValidationError, "threshold geometry"):
            replace(runway, true_bearing_deg=1.0)
