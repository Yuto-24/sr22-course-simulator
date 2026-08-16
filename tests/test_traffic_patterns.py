from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from sr22_course_simulator.aircraft import GeoPosition
from sr22_course_simulator.airport import parse_aip_dms
from sr22_course_simulator.data.airports import RJFM
from sr22_course_simulator.environment import ConstantWind, NoWind
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.examples.miyazaki_traffic_patterns import (
    RJFM_COMBINED_PATTERN_FILENAME,
    RJFM_PATTERN_FILENAMES,
    build_rjfm_normal_patterns,
    rjfm_normal_pattern_specs,
    write_rjfm_normal_pattern_kmls,
)
from sr22_course_simulator.export import reference_paths_to_kml
from sr22_course_simulator.geometry import distance_m, enu_displacement
from sr22_course_simulator.path import PatternLabel, PatternSide, generate_traffic_pattern
from sr22_course_simulator.units import feet_to_metres, nautical_miles_to_metres


KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


class AipMasterDataTests(unittest.TestCase):
    def test_aip_dms_parser_accepts_rjfm_formats(self) -> None:
        self.assertAlmostEqual(
            parse_aip_dms("315234.26N"),
            31.0 + 52.0 / 60.0 + 34.26 / 3_600.0,
        )
        self.assertAlmostEqual(
            parse_aip_dms("1312607.02E"),
            131.0 + 26.0 / 60.0 + 7.02 / 3_600.0,
        )
        self.assertAlmostEqual(parse_aip_dms("315238N"), 31.0 + 52.0 / 60.0 + 38.0 / 3_600.0)
        self.assertEqual(parse_aip_dms("000000S"), 0.0)
        self.assertEqual(parse_aip_dms("0010000W"), -1.0)

    def test_aip_dms_parser_rejects_invalid_fields(self) -> None:
        for value in ("315260N", "1312660E", "912000N", "1810000E", "315238"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_aip_dms(value)

    def test_rjfm_thresholds_and_midpoint_match_transcription(self) -> None:
        runway_09 = RJFM.runway("09")
        runway_27 = RJFM.runway("27")
        self.assertAlmostEqual(runway_09.threshold_a.latitude_deg, parse_aip_dms("315234.26N"))
        self.assertAlmostEqual(runway_09.threshold_a.longitude_deg, parse_aip_dms("1312607.02E"))
        self.assertEqual(runway_09.threshold_b, runway_27.threshold_a)
        self.assertEqual(runway_09.threshold_a, runway_27.threshold_b)
        self.assertEqual(runway_09.center_point, runway_27.center_point)
        self.assertAlmostEqual(
            runway_09.center_point.latitude_deg,
            (runway_09.threshold_a.latitude_deg + runway_09.threshold_b.latitude_deg) / 2.0,
        )
        self.assertAlmostEqual(
            runway_09.center_point.longitude_deg,
            (runway_09.threshold_a.longitude_deg + runway_09.threshold_b.longitude_deg) / 2.0,
        )

    def test_runway_length_and_arp_distance_are_sanity_checks(self) -> None:
        runway = RJFM.runway("09")
        self.assertAlmostEqual(runway.measured_length_m, 2_500.0, delta=15.0)
        self.assertAlmostEqual(
            distance_m(RJFM.reference_point, runway.threshold_a),
            1_250.0,
            delta=40.0,
        )

    def test_magnetic_variation_uses_east_positive_convention(self) -> None:
        self.assertAlmostEqual(RJFM.variation_at(2020.0), -7.0)
        self.assertAlmostEqual(RJFM.variation_at(2026.0), -7.5)
        self.assertAlmostEqual(
            RJFM.true_to_magnetic(85.18, year=2026.0),
            92.68,
        )


class TrafficPatternGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.specs = rjfm_normal_pattern_specs()
        cls.paths = build_rjfm_normal_patterns()

    def test_four_direction_and_side_combinations_are_explicit(self) -> None:
        combinations = tuple(
            (spec.runway.designation, spec.label, spec.side) for spec in self.specs
        )
        self.assertEqual(
            combinations,
            (
                ("09", PatternLabel.NORTH, PatternSide.LEFT),
                ("09", PatternLabel.SOUTH, PatternSide.RIGHT),
                ("27", PatternLabel.NORTH, PatternSide.RIGHT),
                ("27", PatternLabel.SOUTH, PatternSide.LEFT),
            ),
        )

    def test_path_has_semantic_points_at_fixed_pattern_altitude(self) -> None:
        expected_labels = (
            "departure_reference",
            "crosswind",
            "downwind",
            "base",
            "final",
            "threshold_return",
        )
        for path in self.paths:
            self.assertEqual(tuple(point.label for point in path.points()), expected_labels)
            for point in path.points():
                self.assertAlmostEqual(point.altitude_m, feet_to_metres(1_000.0))

    def test_north_and_south_paths_use_correct_runway_normals(self) -> None:
        center = RJFM.runway("09").center_point
        for spec, path in zip(self.specs, self.paths, strict=True):
            crosswind = path.points()[1].position
            _, north_m = enu_displacement(center, crosswind)
            if spec.label is PatternLabel.NORTH:
                self.assertGreater(north_m, 0.0)
            else:
                self.assertLess(north_m, 0.0)

    def test_downwind_offset_and_base_extension_match_parameters(self) -> None:
        for path in self.paths:
            points = path.points()
            self.assertAlmostEqual(
                distance_m(points[0].position, points[1].position),
                nautical_miles_to_metres(1.5),
                delta=0.2,
            )
            self.assertAlmostEqual(
                distance_m(points[4].position, points[5].position),
                nautical_miles_to_metres(1.2),
                delta=0.2,
            )

    def test_zero_crosswind_extension_uses_opposite_threshold(self) -> None:
        for spec, path in zip(self.specs, self.paths, strict=True):
            self.assertAlmostEqual(
                distance_m(path.points()[0].position, spec.runway.threshold_b),
                0.0,
                delta=1.0,
            )

    def test_crosswind_extension_is_an_independent_parameter(self) -> None:
        default_spec = self.specs[0]
        extended_spec = replace(default_spec, crosswind_extension_nm=0.4)
        default_path = generate_traffic_pattern(default_spec)
        extended_path = generate_traffic_pattern(extended_spec)
        self.assertAlmostEqual(
            distance_m(
                default_path.points()[0].position,
                extended_path.points()[0].position,
            ),
            nautical_miles_to_metres(0.4),
            delta=0.2,
        )
        self.assertEqual(default_path.points()[2:], extended_path.points()[2:])

    def test_reciprocal_runway_vectors_and_center_are_consistent(self) -> None:
        runway_09 = RJFM.runway("09")
        runway_27 = RJFM.runway("27")
        self.assertEqual(runway_09.center_point, runway_27.center_point)
        for component_09, component_27 in zip(
            runway_09.runway_unit_vector,
            runway_27.runway_unit_vector,
            strict=True,
        ):
            self.assertAlmostEqual(component_09, -component_27, places=12)

    def test_arp_is_reference_only_and_cannot_move_pattern_geometry(self) -> None:
        original_spec = self.specs[0]
        moved_airport = replace(
            original_spec.airport,
            reference_point=GeoPosition(30.0, 130.0),
        )
        moved_arp_spec = replace(original_spec, airport=moved_airport)
        self.assertEqual(
            generate_traffic_pattern(original_spec).points(),
            generate_traffic_pattern(moved_arp_spec).points(),
        )

    def test_wind_has_no_input_or_effect_on_reference_paths(self) -> None:
        before = self.paths
        NoWind().velocity_at(RJFM.reference_point, feet_to_metres(1_000.0), 0.0)
        ConstantWind.from_meteorological_knots(
            from_direction_deg_true=270.0,
            speed_kt=25.0,
        ).velocity_at(RJFM.reference_point, feet_to_metres(1_000.0), 0.0)
        self.assertEqual(build_rjfm_normal_patterns(), before)
        self.assertTrue(all(not hasattr(spec, "wind") for spec in self.specs))


class TrafficPatternKmlTests(unittest.TestCase):
    def test_multi_placemark_kml_contains_all_four_paths(self) -> None:
        paths = build_rjfm_normal_patterns()
        root = ET.fromstring(reference_paths_to_kml(paths, name="RJFM patterns"))
        placemarks = root.findall(".//k:Placemark", namespaces=KML_NS)
        self.assertEqual(len(placemarks), 4)
        self.assertEqual(
            [placemark.findtext("k:name", namespaces=KML_NS) for placemark in placemarks],
            [path.name for path in paths],
        )
        for placemark in placemarks:
            self.assertEqual(
                placemark.findtext(".//k:altitudeMode", namespaces=KML_NS),
                "absolute",
            )

    def test_writer_generates_four_individual_files_and_combined_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            written = write_rjfm_normal_pattern_kmls(directory)
            self.assertEqual(len(written), 5)
            self.assertEqual(
                {path.name for path in written},
                {*RJFM_PATTERN_FILENAMES, RJFM_COMBINED_PATTERN_FILENAME},
            )
            for path in written:
                self.assertEqual(path.parent, Path(directory))
                ET.fromstring(path.read_text(encoding="utf-8"))

    def test_multi_placemark_export_rejects_empty_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one placemark"):
            reference_paths_to_kml(())


if __name__ == "__main__":
    unittest.main()
