from __future__ import annotations

from dataclasses import replace
from itertools import pairwise
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from sr22_course_simulator.aircraft import GeoPosition
from sr22_course_simulator.airport import parse_aip_dms
from sr22_course_simulator.data.airports import RJFM
from sr22_course_simulator.data.airports.rjfm_short_downwind import (
    RJFM_SHORT_DOWNWIND_CIRCLE_TANGENCY,
    RJFM_SHORT_DOWNWIND_COORDINATES,
    RJFM_SHORT_DOWNWIND_ENTRY_RWY27_COORDINATES,
)
from sr22_course_simulator.environment import ConstantWind, NoWind
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.examples.miyazaki_traffic_patterns import (
    RJFM_COMBINED_PATTERN_FILENAME,
    RJFM_PATTERN_FILENAMES,
    RJFM_RWY09_TRAFFIC_PATTERN_STYLE,
    RJFM_RWY27_TRAFFIC_PATTERN_STYLE,
    RJFM_SHORT_DOWNWIND_CIRCLE_FILENAME,
    RJFM_SHORT_DOWNWIND_COMBINED_FILENAME,
    RJFM_SHORT_DOWNWIND_ENTRY_RWY27_FILENAME,
    RJFM_SHORT_DOWNWIND_FILENAME,
    build_rjfm_short_downwind_paths,
    build_rjfm_traffic_patterns,
    rjfm_short_downwind_circle_spec,
    rjfm_traffic_pattern_specs,
    write_rjfm_short_downwind_kmls,
    write_rjfm_traffic_pattern_kmls,
)
from sr22_course_simulator.export import KmlPathStyle, reference_paths_to_kml
from sr22_course_simulator.geometry import displace_position, distance_m, enu_displacement
from sr22_course_simulator.path import (
    PatternLabel,
    PatternSide,
    aiming_marker_distance_m,
    aiming_marker_elevation_ft,
    generate_coordinated_turn_profile,
    generate_traffic_pattern,
)
from sr22_course_simulator.path.traffic_pattern import (
    _LocalPoint,
    _component_with_altitudes,
    generate_traffic_pattern_components,
)
from sr22_course_simulator.provenance import EvidenceKind
from sr22_course_simulator.units import (
    feet_to_metres,
    knots_to_metres_per_second,
    metres_to_nautical_miles,
    nautical_miles_to_metres,
)


KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


def _style_colors_by_placemark(root: ET.Element) -> dict[str, tuple[str, str]]:
    styles = {
        f"#{style.attrib['id']}": (
            style.findtext("k:LineStyle/k:color", namespaces=KML_NS),
            style.findtext("k:PolyStyle/k:color", namespaces=KML_NS),
        )
        for style in root.findall(".//k:Style", namespaces=KML_NS)
    }
    return {
        placemark.findtext("k:name", namespaces=KML_NS): styles[
            placemark.findtext("k:styleUrl", namespaces=KML_NS)
        ]
        for placemark in root.findall(".//k:Placemark", namespaces=KML_NS)
    }


def _local_coordinates(spec, point) -> tuple[float, float]:
    east_m, north_m = enu_displacement(spec.runway.center_point, point.position)
    runway_east, runway_north = spec.runway.runway_unit_vector
    if spec.side is PatternSide.LEFT:
        normal_east, normal_north = spec.runway.left_normal_unit_vector
    else:
        normal_east, normal_north = spec.runway.right_normal_unit_vector
    return (
        east_m * runway_east + north_m * runway_north,
        east_m * normal_east + north_m * normal_north,
    )


def _labeled_points(path):
    return {point.label: point for point in path.points() if point.label is not None}


def _recovered_path_sweep_deg(spec, path) -> float:
    coordinates = tuple(_local_coordinates(spec, point) for point in path.points())
    return _recovered_coordinate_sweep_deg(coordinates)


def _recovered_coordinate_sweep_deg(coordinates) -> float:
    raw_headings = tuple(
        math.atan2(next_y - y, next_x - x)
        for (x, y), (next_x, next_y) in pairwise(coordinates)
    )
    unwrapped = [raw_headings[0]]
    for previous, current in zip(raw_headings, raw_headings[1:]):
        delta = (current - previous + math.pi) % math.tau - math.pi
        unwrapped.append(unwrapped[-1] + delta)
    return math.degrees(unwrapped[-1] - unwrapped[0])


def _horizontal_path_length_m(spec, points) -> float:
    coordinates = tuple(_local_coordinates(spec, point) for point in points)
    return sum(
        math.hypot(next_x - x, next_y - y)
        for (x, y), (next_x, next_y) in zip(coordinates, coordinates[1:])
    )


def _heading_between(spec, first, second) -> float:
    x, y = _local_coordinates(spec, first)
    next_x, next_y = _local_coordinates(spec, second)
    return math.atan2(next_y - y, next_x - x)


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

    def test_runway_length_and_arp_distance_are_sanity_checks(self) -> None:
        runway = RJFM.runway("09")
        self.assertAlmostEqual(runway.measured_length_m, 2_500.0, delta=15.0)
        self.assertAlmostEqual(distance_m(RJFM.reference_point, runway.threshold_a), 1_250.0, delta=40.0)

    def test_runway_rejects_source_geometry_mismatches(self) -> None:
        runway = RJFM.runway("09")
        with self.assertRaisesRegex(ValidationError, "threshold geometry"):
            replace(runway, true_bearing_deg=runway.true_bearing_deg + 0.2)
        with self.assertRaisesRegex(ValidationError, "threshold geometry"):
            replace(runway, declared_length_m=runway.declared_length_m + 16.0)

    def test_magnetic_variation_uses_east_positive_convention(self) -> None:
        self.assertAlmostEqual(RJFM.variation_at(2020.0), -7.0)
        self.assertAlmostEqual(RJFM.variation_at(2026.0), -7.5)
        self.assertAlmostEqual(RJFM.true_to_magnetic(85.18, year=2026.0), 92.68)


class CoordinatedTurnProfileTests(unittest.TestCase):
    def test_110_ktas_radii_match_30_and_25_degree_banks(self) -> None:
        spec = rjfm_traffic_pattern_specs()[0]
        self.assertAlmostEqual(metres_to_nautical_miles(spec.normal_turn_radius_m), 0.30539456, places=7)
        self.assertAlmostEqual(metres_to_nautical_miles(spec.final_turn_radius_m), 0.37811868, places=7)

    def test_roll_profile_reaches_bank_at_ten_degrees_per_second_and_rolls_out(self) -> None:
        profile = generate_coordinated_turn_profile(
            true_airspeed_mps=knots_to_metres_per_second(110.0),
            nominal_bank_deg=30.0,
            roll_rate_deg_s=10.0,
            signed_sweep_deg=-630.0,
            sample_interval_s=0.25,
            marker_sweeps_deg=(360.0,),
        )
        by_time = {round(sample.elapsed_s, 8): sample for sample in profile.samples}
        self.assertAlmostEqual(math.degrees(by_time[0.25].bank_rad), -2.5)
        self.assertAlmostEqual(math.degrees(by_time[3.0].bank_rad), -30.0)
        self.assertAlmostEqual(math.degrees(profile.samples[-1].bank_rad), 0.0)
        self.assertAlmostEqual(math.degrees(profile.signed_sweep_rad), -630.0)
        self.assertIs(profile.evidence, EvidenceKind.PHYSICS_DERIVED)

    def test_turn_profile_rejects_invalid_or_unreachable_inputs(self) -> None:
        with self.assertRaises(ValidationError):
            generate_coordinated_turn_profile(
                true_airspeed_mps=0.0,
                nominal_bank_deg=30.0,
                roll_rate_deg_s=10.0,
                signed_sweep_deg=90.0,
                sample_interval_s=0.25,
            )
        with self.assertRaisesRegex(ValidationError, "too small"):
            generate_coordinated_turn_profile(
                true_airspeed_mps=knots_to_metres_per_second(110.0),
                nominal_bank_deg=80.0,
                roll_rate_deg_s=1.0,
                signed_sweep_deg=90.0,
                sample_interval_s=0.25,
            )


class TrafficPatternGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.specs = rjfm_traffic_pattern_specs()
        cls.paths = build_rjfm_traffic_patterns()

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

    def test_each_path_contains_the_required_turns_in_order(self) -> None:
        expected = (
            "takeoff_aiming_marker",
            "departure_turn_start",
            "departure_turn_end",
            "before_downwind_turn_start",
            "before_downwind_circle_complete",
            "before_downwind_turn_end",
            "middle_downwind_turn_start",
            "middle_downwind_circle_complete",
            "before_base_turn_start",
            "before_base_turn_end",
            "final_turn_start",
            "final_turn_end",
            "landing_threshold",
            "aiming_marker",
        )
        for path in self.paths:
            labels = tuple(point.label for point in path.points() if point.label)
            self.assertEqual(labels, expected)
            self.assertGreater(len(path.points()), 1_000)

    def test_make_circle_switches_control_each_location_independently(self) -> None:
        def recovered_sweep_deg(path, start_label: str, end_label: str) -> float:
            points = path.points()
            indices = {
                point.label: index for index, point in enumerate(points) if point.label
            }
            coordinates = tuple(
                _local_coordinates(spec, point)
                for point in points[indices[start_label] : indices[end_label] + 1]
            )
            raw_headings = tuple(
                math.atan2(next_y - y, next_x - x)
                for (x, y), (next_x, next_y) in zip(
                    coordinates, coordinates[1:]
                )
            )
            unwrapped = [raw_headings[0]]
            for heading in raw_headings[1:]:
                delta = (heading - raw_headings[len(unwrapped) - 1] + math.pi) % math.tau - math.pi
                unwrapped.append(unwrapped[-1] + delta)
            return math.degrees(unwrapped[-1] - unwrapped[0])

        for before_downwind in (False, True):
            for middle_downwind in (False, True):
                for before_base in (False, True):
                    with self.subTest(
                        before_downwind=before_downwind,
                        middle_downwind=middle_downwind,
                        before_base=before_base,
                    ):
                        spec = rjfm_traffic_pattern_specs(
                            make_circle_before_downwind=before_downwind,
                            make_circle_middle_downwind=middle_downwind,
                            make_circle_before_base=before_base,
                        )[0]
                        path = generate_traffic_pattern(spec)
                        points = path.points()
                        point_indices = {
                            point.label: index
                            for index, point in enumerate(points)
                            if point.label
                        }
                        labels = {
                            point.label for point in points if point.label
                        }
                        self.assertEqual(
                            "before_downwind_circle_complete" in labels,
                            before_downwind,
                        )
                        self.assertEqual(
                            "middle_downwind_turn_start" in labels,
                            middle_downwind,
                        )
                        self.assertEqual(
                            "middle_downwind_circle_complete" in labels,
                            middle_downwind,
                        )
                        self.assertEqual(
                            "before_base_circle_complete" in labels,
                            before_base,
                        )
                        self.assertAlmostEqual(
                            recovered_sweep_deg(
                                path,
                                "before_downwind_turn_start",
                                "before_downwind_turn_end",
                            ),
                            -630.0 if before_downwind else -270.0,
                            delta=0.1,
                        )
                        self.assertAlmostEqual(
                            recovered_sweep_deg(
                                path,
                                "before_base_turn_start",
                                "before_base_turn_end",
                            ),
                            -630.0 if before_base else -270.0,
                            delta=0.1,
                        )
                        if middle_downwind:
                            self.assertAlmostEqual(
                                recovered_sweep_deg(
                                    path,
                                    "middle_downwind_turn_start",
                                    "middle_downwind_circle_complete",
                                ),
                                -360.0,
                                delta=0.1,
                            )
                        else:
                            self.assertEqual(
                                point_indices["before_base_turn_start"],
                                point_indices["before_downwind_turn_end"] + 1,
                            )

                        half_runway = spec.runway.measured_length_m / 2.0
                        departure_station = (
                            half_runway
                            + nautical_miles_to_metres(
                                spec.crosswind_base_extension_nm
                            )
                        )
                        base_station = (
                            -half_runway
                            - nautical_miles_to_metres(
                                spec.crosswind_base_extension_nm
                            )
                        )
                        downwind_offset = nautical_miles_to_metres(
                            spec.downwind_offset_nm
                        )
                        labeled = _labeled_points(path)
                        before_downwind_start = _local_coordinates(
                            spec, labeled["before_downwind_turn_start"]
                        )
                        before_downwind_end = _local_coordinates(
                            spec, labeled["before_downwind_turn_end"]
                        )
                        before_base_start = _local_coordinates(
                            spec, labeled["before_base_turn_start"]
                        )
                        before_base_end = _local_coordinates(
                            spec, labeled["before_base_turn_end"]
                        )
                        self.assertAlmostEqual(
                            before_downwind_start[0], departure_station, delta=0.3
                        )
                        self.assertAlmostEqual(
                            before_downwind_end[1], downwind_offset, delta=0.3
                        )
                        self.assertAlmostEqual(
                            before_base_start[1], downwind_offset, delta=0.3
                        )
                        self.assertAlmostEqual(
                            before_base_end[0], base_station, delta=0.3
                        )

                        self.assertAlmostEqual(
                            distance_m(points[0].position, points[-1].position),
                            0.0,
                            delta=0.01,
                        )
                        self.assertAlmostEqual(
                            points[0].altitude_m, points[-1].altitude_m, places=9
                        )
                        descent = tuple(
                            point.altitude_m
                            for point in points[
                                point_indices["before_base_turn_start"]
                                : point_indices["final_turn_end"] + 1
                            ]
                        )
                        self.assertTrue(
                            all(a >= b for a, b in zip(descent, descent[1:]))
                        )

    def test_make_circle_switches_require_actual_booleans(self) -> None:
        spec = self.specs[0]
        for field_name in (
            "make_circle_before_downwind",
            "make_circle_middle_downwind",
            "make_circle_before_base",
            "make_270_before_downwind",
            "make_270_before_base",
        ):
            with self.subTest(field_name=field_name), self.assertRaisesRegex(
                ValidationError, f"{field_name} must be bool"
            ):
                replace(spec, **{field_name: 1})

    def test_all_32_circle_and_make_270_combinations_generate(self) -> None:
        for before_downwind in (False, True):
            for make_270_downwind in (False, True):
                for middle_downwind in (False, True):
                    for before_base in (False, True):
                        for make_270_base in (False, True):
                            with self.subTest(
                                before_downwind=before_downwind,
                                make_270_downwind=make_270_downwind,
                                middle_downwind=middle_downwind,
                                before_base=before_base,
                                make_270_base=make_270_base,
                            ):
                                spec = rjfm_traffic_pattern_specs(
                                    make_circle_before_downwind=before_downwind,
                                    make_270_before_downwind=make_270_downwind,
                                    make_circle_middle_downwind=middle_downwind,
                                    make_circle_before_base=before_base,
                                    make_270_before_base=make_270_base,
                                )[0]
                                path = generate_traffic_pattern(spec)
                                points = path.points()
                                indices = {
                                    point.label: index
                                    for index, point in enumerate(points)
                                    if point.label
                                }
                                self.assertEqual(
                                    "before_downwind_circle_complete" in indices,
                                    before_downwind and make_270_downwind,
                                )
                                self.assertEqual(
                                    "before_downwind_turn_start" in indices,
                                    make_270_downwind or before_downwind,
                                )
                                self.assertEqual(
                                    "downwind_turn_start" in indices,
                                    not (make_270_downwind or before_downwind),
                                )
                                self.assertEqual(
                                    "before_base_circle_complete" in indices,
                                    before_base and make_270_base,
                                )
                                self.assertEqual(
                                    "before_base_turn_start" in indices,
                                    make_270_base or before_base,
                                )
                                self.assertEqual(
                                    "base_turn_start" in indices,
                                    not (make_270_base or before_base),
                                )
                                descent_start = indices[
                                    "before_base_turn_end"
                                    if before_base and not make_270_base
                                    else "before_base_turn_start"
                                    if make_270_base
                                    else "base_turn_start"
                                ]
                                final_end = indices["final_turn_end"]
                                descending = tuple(
                                    point.altitude_m
                                    for point in points[descent_start : final_end + 1]
                                )
                                self.assertTrue(
                                    all(a >= b for a, b in zip(descending, descending[1:]))
                                )
                                self.assertAlmostEqual(
                                    distance_m(points[0].position, points[-1].position),
                                    0.0,
                                    delta=0.01,
                                )

    def test_circle_and_270_components_are_independent(self) -> None:
        for location in ("before_downwind", "before_base"):
            with self.subTest(location=location):
                spec = rjfm_traffic_pattern_specs(
                    make_circle_before_downwind=location == "before_downwind",
                    make_270_before_downwind=False,
                    make_circle_middle_downwind=False,
                    make_circle_before_base=location == "before_base",
                    make_270_before_base=False,
                )[0]
                components = generate_traffic_pattern_components(spec)
                self.assertEqual(len(components), 2)
                self.assertIn("Circle", components[1].name)
                self.assertNotIn("270", components[1].name)

    def test_all_32_independent_component_combinations_generate(self) -> None:
        switch_sets = tuple(
            (before_downwind, middle_downwind, before_base, downwind_270, base_270)
            for before_downwind in (False, True)
            for middle_downwind in (False, True)
            for before_base in (False, True)
            for downwind_270 in (False, True)
            for base_270 in (False, True)
        )
        for pattern_index in range(4):
            for switches in switch_sets:
                with self.subTest(pattern_index=pattern_index, switches=switches):
                    spec = rjfm_traffic_pattern_specs(
                        make_circle_before_downwind=switches[0],
                        make_circle_middle_downwind=switches[1],
                        make_circle_before_base=switches[2],
                        make_270_before_downwind=switches[3],
                        make_270_before_base=switches[4],
                    )[pattern_index]
                    components = generate_traffic_pattern_components(spec)
                    self.assertEqual(len(components), 1 + sum(switches))
                    base_labels = {
                        point.label for point in components[0].points() if point.label
                    }
                    self.assertIn("downwind_turn_start", base_labels)
                    self.assertIn("base_turn_start", base_labels)
                    self.assertFalse(
                        any("circle" in label or "before_" in label for label in base_labels)
                    )

    def test_independent_components_retain_exact_turn_roles_and_altitudes(self) -> None:
        spec = rjfm_traffic_pattern_specs(make_circle_before_base=True)[0]
        named = {
            path.name: path for path in generate_traffic_pattern_components(spec)
        }
        base = next(path for path in named.values() if "No Circle / No 270" in path.name)
        base_labels = _labeled_points(base)
        self.assertIn("downwind_turn_start", base_labels)
        self.assertIn("base_turn_start", base_labels)

        for path in named.values():
            if "Circle" in path.name and "No Circle" not in path.name:
                self.assertAlmostEqual(
                    _recovered_path_sweep_deg(spec, path),
                    -360.0,
                    delta=0.1,
                )
                self.assertTrue(
                    all(
                        point.altitude_m == feet_to_metres(spec.altitude_ft)
                        for point in path.points()
                    )
                )

        before_base_270 = next(
            path for path in named.values() if path.name.endswith("Before Base 270")
        )
        before_base_270_labels = _labeled_points(before_base_270)
        self.assertIn("before_base_branch", before_base_270_labels)
        self.assertIn("before_base_merge", before_base_270_labels)
        self.assertIn("before_base_descent_start", before_base_270_labels)
        self.assertAlmostEqual(
            before_base_270_labels["before_base_merge"].altitude_m,
            base_labels["base_turn_end"].altitude_m,
            places=9,
        )
        before_downwind_circle = next(
            path
            for path in named.values()
            if path.name.endswith("Before Downwind Circle")
        )
        before_base_circle = next(
            path for path in named.values() if path.name.endswith("Before Base Circle")
        )
        self.assertAlmostEqual(
            distance_m(
                before_downwind_circle.points()[0].position,
                _labeled_points(
                    next(
                        path
                        for path in named.values()
                        if path.name.endswith("Before Downwind 270")
                    )
                )["before_downwind_turn_start"].position,
            ),
            0.0,
            delta=0.02,
        )
        self.assertAlmostEqual(
            distance_m(
                before_base_circle.points()[0].position,
                before_base_270_labels["before_base_turn_start"].position,
            ),
            0.0,
            delta=0.02,
        )

    def test_components_keep_the_normal_placemark_identical_for_all_switches(self) -> None:
        switch_sets = tuple(
            (before_downwind, middle_downwind, before_base, downwind_270, base_270)
            for before_downwind in (False, True)
            for middle_downwind in (False, True)
            for before_base in (False, True)
            for downwind_270 in (False, True)
            for base_270 in (False, True)
        )
        for pattern_index in range(4):
            expected = None
            for switches in switch_sets:
                spec = rjfm_traffic_pattern_specs(
                    make_circle_before_downwind=switches[0],
                    make_circle_middle_downwind=switches[1],
                    make_circle_before_base=switches[2],
                    make_270_before_downwind=switches[3],
                    make_270_before_base=switches[4],
                )[pattern_index]
                base = generate_traffic_pattern_components(spec)[0]
                if expected is None:
                    expected = base.points()
                self.assertEqual(base.points(), expected)

    def test_circle_uses_the_latent_270_start_and_inbound_heading(self) -> None:
        for spec in rjfm_traffic_pattern_specs(
            make_circle_before_downwind=True,
            make_circle_middle_downwind=False,
            make_circle_before_base=True,
            make_270_before_downwind=False,
            make_270_before_base=False,
        ):
            components = generate_traffic_pattern_components(spec)
            for location, heading, bank_deg in (
                ("Downwind", math.pi / 2.0, spec.downwind_turn_bank_deg),
                ("Base", math.pi, spec.base_turn_bank_deg),
            ):
                circle = next(
                    path for path in components if path.name.endswith(f"Before {location} Circle")
                )
                potential = generate_traffic_pattern_components(
                    replace(
                        spec,
                        make_circle_before_downwind=False,
                        make_circle_before_base=False,
                        make_270_before_downwind=location == "Downwind",
                        make_270_before_base=location == "Base",
                    )
                )[-1]
                potential_labels = _labeled_points(potential)
                start_label = f"before_{location.lower()}_turn_start"
                start_index = next(
                    index
                    for index, point in enumerate(potential.points())
                    if point.label == start_label
                )
                self.assertAlmostEqual(
                    distance_m(
                        circle.points()[0].position,
                        potential_labels[start_label].position,
                    ),
                    0.0,
                    delta=0.02,
                )
                self.assertLess(
                    abs(
                        math.sin(
                            _heading_between(spec, circle.points()[0], circle.points()[1])
                            - _heading_between(
                                spec,
                                potential.points()[start_index],
                                potential.points()[start_index + 1],
                            )
                        )
                    ),
                    0.001,
                )
                self.assertLess(
                    abs(math.sin(_heading_between(spec, circle.points()[0], circle.points()[1]) - heading)),
                    0.03,
                )
                profile = generate_coordinated_turn_profile(
                    true_airspeed_mps=knots_to_metres_per_second(spec.true_airspeed_kt),
                    nominal_bank_deg=bank_deg,
                    roll_rate_deg_s=spec.roll_rate_deg_s,
                    signed_sweep_deg=-360.0,
                    sample_interval_s=spec.sample_interval_s,
                )
                self.assertEqual(len(circle.points()), len(profile.samples))

    def test_circle_only_switches_generate_standalone_circles_and_legacy_turns(self) -> None:
        for location in ("downwind", "base"):
            with self.subTest(location=location):
                spec = rjfm_traffic_pattern_specs(
                    make_circle_before_downwind=location == "downwind",
                    make_circle_middle_downwind=False,
                    make_circle_before_base=location == "base",
                    make_270_before_downwind=False,
                    make_270_before_base=False,
                )[0]
                components = generate_traffic_pattern_components(spec)
                component_names = tuple(path.name for path in components)
                self.assertEqual(len(components), 2)
                self.assertTrue(
                    any(
                        name.endswith(f"Before {location.title()} Circle")
                        for name in component_names
                    )
                )
                self.assertFalse(any(name.endswith("270") for name in component_names))

                legacy_path = generate_traffic_pattern(spec)
                legacy_labels = _labeled_points(legacy_path)
                self.assertIn(f"before_{location}_turn_start", legacy_labels)
                legacy_points = legacy_path.points()
                indices = {
                    point.label: index
                    for index, point in enumerate(legacy_points)
                    if point.label is not None
                }
                coordinates = tuple(
                    _local_coordinates(spec, point)
                    for point in legacy_points[
                        indices[f"before_{location}_turn_start"] : indices[
                            f"before_{location}_turn_end"
                        ]
                        + 1
                    ]
                )
                self.assertAlmostEqual(
                    _recovered_coordinate_sweep_deg(coordinates),
                    -360.0,
                    delta=0.1,
                )

    def test_circle_only_retains_tangent_ordinary_transitions(self) -> None:
        for location in ("downwind", "base"):
            for sample_interval_s in (0.125, 0.25):
                specs = rjfm_traffic_pattern_specs(
                    make_circle_before_downwind=location == "downwind",
                    make_circle_middle_downwind=False,
                    make_circle_before_base=location == "base",
                    make_270_before_downwind=False,
                    make_270_before_base=False,
                    sample_interval_s=sample_interval_s,
                )
                for spec in specs:
                    with self.subTest(location=location, name=spec.name,
                                      sample_interval_s=sample_interval_s):
                        points = generate_traffic_pattern(spec).points()
                        indices = {p.label: i for i, p in enumerate(points) if p.label}
                        start = indices[f"before_{location}_turn_start"]
                        circle_end = indices[f"before_{location}_turn_end"]
                        if location == "base":
                            pattern_altitude = feet_to_metres(spec.altitude_ft)
                            for point in points[start:circle_end + 1]:
                                self.assertAlmostEqual(point.altitude_m, pattern_altitude)
                            self.assertLess(points[circle_end + 1].altitude_m, pattern_altitude)
                        # The circle endpoint also starts the ordinary turn.
                        turn_end = indices[f"{location}_turn_end"]
                        for first, last, sweep in (
                            (start, circle_end, -360.0),
                            (circle_end, turn_end, 90.0),
                        ):
                            self.assertAlmostEqual(
                                _recovered_coordinate_sweep_deg(tuple(
                                    _local_coordinates(spec, p)
                                    for p in points[first:last + 1]
                                )), sweep, delta=0.1,
                            )
                        # Signed local heading differences catch both diagonal
                        # connectors and reversed (180-degree) tangencies.
                        for index in (start, circle_end, turn_end):
                            before = _heading_between(spec, points[index - 1], points[index])
                            after = _heading_between(spec, points[index], points[index + 1])
                            delta = (after - before + math.pi) % math.tau - math.pi
                            self.assertAlmostEqual(math.degrees(delta), 0.0, delta=0.1)
                        outbound = math.pi if location == "downwind" else 1.5 * math.pi
                        heading = _heading_between(spec, points[turn_end], points[turn_end + 1])
                        delta = (heading - outbound + math.pi) % math.tau - math.pi
                        self.assertAlmostEqual(math.degrees(delta), 0.0, delta=0.1)
                        # Every point in both turns is sampled: a long chord
                        # cannot hide between the circle and ordinary rollout.
                        max_step = knots_to_metres_per_second(spec.true_airspeed_kt) * sample_interval_s
                        for first, second in pairwise(points[start:turn_end + 1]):
                            self.assertLessEqual(
                                _horizontal_path_length_m(spec, (first, second)),
                                max_step + 0.01,
                            )

    def test_location_specific_turn_banks_control_circle_and_270_profiles(self) -> None:
        spec = rjfm_traffic_pattern_specs(
            downwind_turn_bank_deg=20.0,
            base_turn_bank_deg=24.0,
            make_circle_before_downwind=True,
            make_circle_middle_downwind=True,
            make_circle_before_base=True,
            make_270_before_downwind=True,
            make_270_before_base=True,
        )[0]
        components = {path.name: path for path in generate_traffic_pattern_components(spec)}
        expected_profiles = {
            "Before Downwind Circle": generate_coordinated_turn_profile(
                true_airspeed_mps=knots_to_metres_per_second(spec.true_airspeed_kt),
                nominal_bank_deg=spec.downwind_turn_bank_deg,
                roll_rate_deg_s=spec.roll_rate_deg_s,
                signed_sweep_deg=-360.0,
                sample_interval_s=spec.sample_interval_s,
            ),
            "Before Base Circle": generate_coordinated_turn_profile(
                true_airspeed_mps=knots_to_metres_per_second(spec.true_airspeed_kt),
                nominal_bank_deg=spec.base_turn_bank_deg,
                roll_rate_deg_s=spec.roll_rate_deg_s,
                signed_sweep_deg=-360.0,
                sample_interval_s=spec.sample_interval_s,
            ),
        }
        for suffix, profile in expected_profiles.items():
            path = next(path for name, path in components.items() if name.endswith(suffix))
            self.assertEqual(len(path.points()), len(profile.samples))

        for location, bank_deg in (
            ("Downwind", spec.downwind_turn_bank_deg),
            ("Base", spec.base_turn_bank_deg),
        ):
            profile = generate_coordinated_turn_profile(
                true_airspeed_mps=knots_to_metres_per_second(spec.true_airspeed_kt),
                nominal_bank_deg=bank_deg,
                roll_rate_deg_s=spec.roll_rate_deg_s,
                signed_sweep_deg=-270.0,
                sample_interval_s=spec.sample_interval_s,
            )
            path = next(
                path
                for name, path in components.items()
                if name.endswith(f"Before {location} 270")
            )
            labels = _labeled_points(path)
            start = next(
                index
                for index, point in enumerate(path.points())
                if point.label == f"before_{location.lower()}_turn_start"
            )
            end = next(
                index
                for index, point in enumerate(path.points())
                if point.label == f"before_{location.lower()}_turn_end"
            )
            self.assertEqual(end - start + 1, len(profile.samples))
            self.assertIn(f"before_{location.lower()}_turn_start", labels)

    def test_270_components_connect_tangentially_and_apply_required_altitudes(self) -> None:
        for spec in rjfm_traffic_pattern_specs(
            make_circle_before_downwind=False,
            make_circle_middle_downwind=False,
            make_circle_before_base=False,
            make_270_before_downwind=True,
            make_270_before_base=True,
        ):
            components = generate_traffic_pattern_components(spec)
            base = components[0]
            base_labels = _labeled_points(base)
            for location, heading, branch_label, merge_label in (
                ("downwind", math.pi / 2.0, "downwind_turn_start", "downwind_turn_end"),
                ("base", math.pi, "base_turn_start", "base_turn_end"),
            ):
                component = next(
                    path for path in components if path.name.endswith(f"Before {location.title()} 270")
                )
                labels = _labeled_points(component)
                prefix = f"before_{location}"
                self.assertAlmostEqual(
                    distance_m(component.points()[0].position, base_labels[branch_label].position),
                    0.0,
                    delta=0.02,
                )
                self.assertAlmostEqual(
                    distance_m(component.points()[-1].position, base_labels[merge_label].position),
                    0.0,
                    delta=0.02,
                )
                start_index = next(
                    index for index, point in enumerate(component.points())
                    if point.label == f"{prefix}_turn_start"
                )
                end_index = next(
                    index for index, point in enumerate(component.points())
                    if point.label == f"{prefix}_turn_end"
                )
                self.assertLess(
                    abs(math.sin(_heading_between(spec, component.points()[0], component.points()[1]) - heading)),
                    0.03,
                )
                self.assertLess(
                    abs(math.sin(_heading_between(spec, component.points()[start_index], component.points()[start_index + 1]) - heading)),
                    0.03,
                )
                outbound_heading = heading - 3.0 * math.pi / 2.0
                self.assertLess(
                    abs(math.sin(_heading_between(spec, component.points()[end_index - 1], component.points()[end_index]) - outbound_heading)),
                    0.03,
                )
                self.assertLess(
                    abs(math.sin(_heading_between(spec, component.points()[-2], component.points()[-1]) - outbound_heading)),
                    0.03,
                )
                self.assertAlmostEqual(
                    _recovered_path_sweep_deg(
                        spec,
                        type(component)(
                            name="arc",
                            path_points=component.points()[start_index : end_index + 1],
                        ),
                    ),
                    -270.0,
                    delta=0.1,
                )
                expected_profile = generate_coordinated_turn_profile(
                    true_airspeed_mps=knots_to_metres_per_second(spec.true_airspeed_kt),
                    nominal_bank_deg=spec.downwind_turn_bank_deg,
                    roll_rate_deg_s=spec.roll_rate_deg_s,
                    signed_sweep_deg=-270.0,
                    sample_interval_s=spec.sample_interval_s,
                )
                self.assertEqual(end_index - start_index + 1, len(expected_profile.samples))

            before_downwind = next(
                path for path in components if path.name.endswith("Before Downwind 270")
            )
            self.assertTrue(
                all(
                    point.altitude_m == feet_to_metres(spec.altitude_ft)
                    for point in before_downwind.points()
                )
            )
            before_base = next(path for path in components if path.name.endswith("Before Base 270"))
            before_base_labels = _labeled_points(before_base)
            base_points = base.points()
            start = next(index for index, point in enumerate(base_points) if point.label == "base_turn_start")
            end = next(index for index, point in enumerate(base_points) if point.label == "base_turn_end")
            descent_start = next(
                index
                for index, point in enumerate(before_base.points())
                if point.label == "before_base_descent_start"
            )
            self.assertAlmostEqual(
                _horizontal_path_length_m(spec, before_base.points()[descent_start:]),
                _horizontal_path_length_m(spec, base_points[start : end + 1]),
                places=6,
            )
            self.assertTrue(
                all(
                    point.altitude_m == feet_to_metres(spec.altitude_ft)
                    for point in before_base.points()[: descent_start + 1]
                )
            )
            self.assertAlmostEqual(
                before_base.points()[-1].altitude_m,
                base_labels["base_turn_end"].altitude_m,
                places=9,
            )
            self.assertTrue(
                all(
                    first.altitude_m >= second.altitude_m
                    for first, second in zip(before_base.points(), before_base.points()[1:])
                )
            )

    def test_before_base_270_rejects_a_shorter_alternative_path(self) -> None:
        spec = rjfm_traffic_pattern_specs()[0]
        with self.assertRaisesRegex(ValidationError, "shorter than the ordinary Base-turn"):
            _component_with_altitudes(
                spec,
                name="short alternative",
                local_points=(
                    _LocalPoint(0.0, 0.0),
                    _LocalPoint(100.0, 0.0),
                ),
                descent_distance_m=101.0,
                merge_altitude_m=200.0,
            )

    def test_make_270_before_downwind_off_uses_level_110kt_22deg_turn(self) -> None:
        spec = rjfm_traffic_pattern_specs(
            true_airspeed_kt=110.0,
            normal_bank_deg=30.0,
            downwind_turn_bank_deg=22.0,
            make_circle_before_downwind=False,
            make_270_before_downwind=False,
        )[0]
        path = generate_traffic_pattern(spec)
        points = path.points()
        indices = {
            point.label: index
            for index, point in enumerate(points)
            if point.label
        }
        self.assertNotIn("before_downwind_turn_start", indices)
        self.assertNotIn("before_downwind_circle_complete", indices)
        self.assertAlmostEqual(spec.downwind_turn_radius_m, 808.22466759, places=5)
        start = indices["downwind_turn_start"]
        end = indices["downwind_turn_end"]
        self.assertTrue(
            all(
                point.altitude_m == feet_to_metres(1_000.0)
                for point in points[start : end + 1]
            )
        )
        coordinates = tuple(
            _local_coordinates(spec, point)
            for point in points[start : end + 1]
        )
        headings = tuple(
            math.atan2(next_y - y, next_x - x)
            for (x, y), (next_x, next_y) in zip(coordinates, coordinates[1:])
        )
        unwrapped = [headings[0]]
        for heading in headings[1:]:
            delta = (heading - unwrapped[-1] + math.pi) % math.tau - math.pi
            unwrapped.append(unwrapped[-1] + delta)
        self.assertAlmostEqual(
            math.degrees(unwrapped[-1] - unwrapped[0]),
            90.0,
            delta=0.1,
        )

    def test_make_270_off_uses_ordinary_110kt_22deg_base_turn_and_descent(self) -> None:
        spec = rjfm_traffic_pattern_specs(
            true_airspeed_kt=110.0,
            normal_bank_deg=30.0,
            base_turn_bank_deg=22.0,
            make_circle_before_base=False,
            make_270_before_base=False,
        )[0]
        path = generate_traffic_pattern(spec)
        points = path.points()
        indices = {
            point.label: index
            for index, point in enumerate(points)
            if point.label
        }
        self.assertNotIn("before_base_turn_start", indices)
        self.assertNotIn("before_base_circle_complete", indices)
        self.assertIn("base_turn_start", indices)
        self.assertIn("base_turn_end", indices)
        self.assertAlmostEqual(spec.base_turn_radius_m, 808.22466759, places=5)

        start = indices["base_turn_start"]
        end = indices["base_turn_end"]
        coordinates = tuple(
            _local_coordinates(spec, point)
            for point in points[start : end + 1]
        )
        headings = tuple(
            math.atan2(next_y - y, next_x - x)
            for (x, y), (next_x, next_y) in zip(
                coordinates, coordinates[1:]
            )
        )
        unwrapped = [headings[0]]
        for heading in headings[1:]:
            delta = (heading - unwrapped[-1] + math.pi) % math.tau - math.pi
            unwrapped.append(unwrapped[-1] + delta)
        self.assertAlmostEqual(
            math.degrees(unwrapped[-1] - unwrapped[0]),
            90.0,
            delta=0.1,
        )
        self.assertAlmostEqual(points[start].altitude_m, feet_to_metres(1_000.0))
        self.assertLess(points[start + 1].altitude_m, points[start].altitude_m)

    def test_turns_are_tangent_to_preserved_leg_axes(self) -> None:
        for spec, path in zip(self.specs, self.paths, strict=True):
            labels = _labeled_points(path)
            half_runway = spec.runway.measured_length_m / 2.0
            departure_station = half_runway + 1.2 * 1_852.0
            base_station = -half_runway - 1.2 * 1_852.0
            downwind_offset = 1.5 * 1_852.0

            departure_start = _local_coordinates(spec, labels["departure_turn_start"])
            departure_end = _local_coordinates(spec, labels["departure_turn_end"])
            before_downwind_start = _local_coordinates(spec, labels["before_downwind_turn_start"])
            before_downwind_end = _local_coordinates(spec, labels["before_downwind_turn_end"])
            before_base_start = _local_coordinates(spec, labels["before_base_turn_start"])
            before_base_end = _local_coordinates(spec, labels["before_base_turn_end"])
            final_start = _local_coordinates(spec, labels["final_turn_start"])
            final_end = _local_coordinates(spec, labels["final_turn_end"])

            self.assertAlmostEqual(departure_start[1], 0.0, delta=0.3)
            self.assertAlmostEqual(departure_end[0], departure_station, delta=0.3)
            self.assertAlmostEqual(before_downwind_start[0], departure_station, delta=0.3)
            self.assertAlmostEqual(before_downwind_end[1], downwind_offset, delta=0.3)
            self.assertAlmostEqual(before_base_start[1], downwind_offset, delta=0.3)
            self.assertAlmostEqual(before_base_end[0], base_station, delta=0.3)
            self.assertAlmostEqual(final_start[0], base_station, delta=0.3)
            self.assertAlmostEqual(final_end[1], 0.0, delta=0.3)

    def test_reciprocal_crosswind_and_base_share_each_physical_line(self) -> None:
        by_direction_and_label = {
            (spec.runway.designation, spec.label): (spec, _labeled_points(path))
            for spec, path in zip(self.specs, self.paths, strict=True)
        }
        for label in PatternLabel:
            runway_09, rwy09 = by_direction_and_label[("09", label)]
            runway_27, rwy27 = by_direction_and_label[("27", label)]
            # The far/downwind endpoint is shared exactly.  The near/runway
            # endpoints differ because the 30-degree Crosswind and 25-degree
            # Final turns have different tangent displacements, but their
            # straight legs remain collinear on this common physical axis.
            self.assertAlmostEqual(
                distance_m(
                    rwy09["before_downwind_turn_start"].position,
                    rwy27["before_base_turn_end"].position,
                ),
                0.0,
                delta=0.3,
            )
            for point in (
                rwy09["departure_turn_end"],
                rwy09["before_downwind_turn_start"],
                rwy27["before_base_turn_end"],
                rwy27["final_turn_start"],
            ):
                along_m, _ = _local_coordinates(runway_09, point)
                self.assertAlmostEqual(
                    along_m,
                    runway_09.runway.measured_length_m / 2.0 + 1.2 * 1_852.0,
                    delta=0.3,
                )
            self.assertEqual(runway_09.crosswind_base_extension_nm, 1.2)
            self.assertEqual(runway_27.crosswind_base_extension_nm, 1.2)

    def test_north_and_south_paths_use_correct_runway_normals(self) -> None:
        center = RJFM.runway("09").center_point
        for spec, path in zip(self.specs, self.paths, strict=True):
            point = _labeled_points(path)["middle_downwind_turn_start"].position
            _, north_m = enu_displacement(center, point)
            if spec.label is PatternLabel.NORTH:
                self.assertGreater(north_m, 0.0)
            else:
                self.assertLess(north_m, 0.0)

    def test_middle_circle_starts_and_ends_on_downwind_and_moves_forward(self) -> None:
        for spec, path in zip(self.specs, self.paths, strict=True):
            labels = _labeled_points(path)
            start = _local_coordinates(spec, labels["middle_downwind_turn_start"])
            end = _local_coordinates(spec, labels["middle_downwind_circle_complete"])
            self.assertAlmostEqual(start[1], 1.5 * 1_852.0, delta=0.3)
            self.assertAlmostEqual(end[1], 1.5 * 1_852.0, delta=0.3)
            self.assertAlmostEqual(start[0] - end[0], 127.62265661, places=5)

    def test_generated_turns_embed_required_sweeps_outside_axes_and_tangencies(self) -> None:
        """Check the sampled path, not only standalone turn-profile inputs."""

        for spec, path in zip(self.specs, self.paths, strict=True):
            points = path.points()
            indices = {point.label: index for index, point in enumerate(points) if point.label}
            speed = knots_to_metres_per_second(spec.true_airspeed_kt)
            expected_turns = (
                (
                    "before_downwind_turn_start",
                    "before_downwind_turn_end",
                    "before_downwind_circle_complete",
                    math.pi / 2.0,
                    -630.0,
                    "x_positive",
                    spec.downwind_turn_bank_deg,
                ),
                (
                    "middle_downwind_turn_start",
                    "middle_downwind_circle_complete",
                    None,
                    math.pi,
                    -360.0,
                    "y_positive",
                    spec.downwind_turn_bank_deg,
                ),
                (
                    "before_base_turn_start",
                    "before_base_turn_end",
                    None,
                    math.pi,
                    -270.0,
                    "x_negative",
                    spec.base_turn_bank_deg,
                ),
            )
            for (
                start_label,
                end_label,
                marker_label,
                heading,
                sweep,
                outside,
                bank_deg,
            ) in expected_turns:
                profile = generate_coordinated_turn_profile(
                    true_airspeed_mps=speed,
                    nominal_bank_deg=bank_deg,
                    roll_rate_deg_s=spec.roll_rate_deg_s,
                    signed_sweep_deg=sweep,
                    sample_interval_s=spec.sample_interval_s,
                    marker_sweeps_deg=(360.0,) if marker_label else (),
                )
                start_index = indices[start_label]
                end_index = indices[end_label]
                embedded = points[start_index : end_index + 1]
                self.assertEqual(len(embedded), len(profile.samples))
                self.assertAlmostEqual(math.degrees(profile.signed_sweep_rad), sweep)

                start_x, start_y = _local_coordinates(spec, embedded[0])
                cosine, sine = math.cos(heading), math.sin(heading)
                local_embedded = tuple(_local_coordinates(spec, point) for point in embedded)
                for actual, sample in zip(local_embedded, profile.samples, strict=True):
                    expected_x = start_x + cosine * sample.x_m - sine * sample.y_m
                    expected_y = start_y + sine * sample.x_m + cosine * sample.y_m
                    self.assertAlmostEqual(actual[0], expected_x, delta=0.02)
                    self.assertAlmostEqual(actual[1], expected_y, delta=0.02)

                start_heading = math.atan2(
                    local_embedded[1][1] - local_embedded[0][1],
                    local_embedded[1][0] - local_embedded[0][0],
                )
                end_heading = math.atan2(
                    local_embedded[-1][1] - local_embedded[-2][1],
                    local_embedded[-1][0] - local_embedded[-2][0],
                )
                self.assertLess(abs(math.sin(start_heading - heading)), 0.02)
                self.assertLess(
                    abs(math.sin(end_heading - (heading + profile.signed_sweep_rad))),
                    0.02,
                )

                if outside == "x_positive":
                    self.assertGreater(max(point[0] for point in local_embedded), start_x)
                elif outside == "y_positive":
                    self.assertGreater(max(point[1] for point in local_embedded), start_y)
                else:
                    self.assertLess(min(point[0] for point in local_embedded), start_x)

                if marker_label is not None:
                    marker_offset = indices[marker_label] - start_index
                    self.assertAlmostEqual(
                        abs(math.degrees(profile.samples[marker_offset].heading_change_rad)),
                        360.0,
                        places=7,
                    )
                    self.assertAlmostEqual(
                        abs(math.degrees(profile.samples[marker_offset].bank_rad)),
                        bank_deg,
                        places=7,
                    )

            middle_start = indices["middle_downwind_turn_start"]
            middle_end = indices["middle_downwind_circle_complete"]
            middle_delta = (
                _local_coordinates(spec, points[middle_end])[0]
                - _local_coordinates(spec, points[middle_start])[0]
            )
            self.assertAlmostEqual(middle_delta, -127.62265661, places=5)

    def test_representative_path_geometry_independently_recovers_turn_sweeps(self) -> None:
        """Recover turn behavior from generated coordinates without profile reuse."""

        spec, path = self.specs[0], self.paths[0]
        points = path.points()
        indices = {point.label: index for index, point in enumerate(points) if point.label}

        def headings_between(start_label: str, end_label: str) -> tuple[float, ...]:
            coordinates = tuple(
                _local_coordinates(spec, point)
                for point in points[indices[start_label] : indices[end_label] + 1]
            )
            raw = tuple(
                math.atan2(next_y - y, next_x - x)
                for (x, y), (next_x, next_y) in zip(coordinates, coordinates[1:])
            )
            unwrapped = [raw[0]]
            for heading in raw[1:]:
                delta = (heading - raw[len(unwrapped) - 1] + math.pi) % math.tau - math.pi
                unwrapped.append(unwrapped[-1] + delta)
            return tuple(unwrapped)

        expected = (
            (
                "before_downwind_turn_start",
                "before_downwind_turn_end",
                "before_downwind_circle_complete",
                -630.0,
                math.pi,
                lambda coordinates: max(x for x, _ in coordinates) > coordinates[0][0],
            ),
            (
                "middle_downwind_turn_start",
                "middle_downwind_circle_complete",
                None,
                -360.0,
                math.pi,
                lambda coordinates: max(y for _, y in coordinates) > coordinates[0][1],
            ),
            (
                "before_base_turn_start",
                "before_base_turn_end",
                None,
                -270.0,
                3.0 * math.pi / 2.0,
                lambda coordinates: min(x for x, _ in coordinates) < coordinates[0][0],
            ),
        )
        for start_label, end_label, marker_label, expected_sweep, expected_end_heading, outside in expected:
            headings = headings_between(start_label, end_label)
            coordinates = tuple(
                _local_coordinates(spec, point)
                for point in points[indices[start_label] : indices[end_label] + 1]
            )
            self.assertAlmostEqual(
                math.degrees(headings[-1] - headings[0]), expected_sweep, delta=0.1
            )
            self.assertLess(abs(math.sin(headings[-1] - expected_end_heading)), 0.001)
            self.assertTrue(outside(coordinates))
            if marker_label is not None:
                marker_heading = headings[indices[marker_label] - indices[start_label] - 1]
                self.assertAlmostEqual(
                    math.degrees(marker_heading - headings[0]), -360.0, delta=0.3
                )

    def test_arp_and_wind_cannot_move_reference_path(self) -> None:
        original_spec = self.specs[0]
        moved_airport = replace(
            original_spec.airport,
            reference_point=GeoPosition(30.0, 130.0),
        )
        moved_path = generate_traffic_pattern(replace(original_spec, airport=moved_airport))
        self.assertEqual(generate_traffic_pattern(original_spec).points(), moved_path.points())
        before = self.paths
        NoWind().velocity_at(RJFM.reference_point, feet_to_metres(1_000.0), 0.0)
        ConstantWind.from_meteorological_knots(
            from_direction_deg_true=270.0,
            speed_kt=25.0,
        ).velocity_at(RJFM.reference_point, feet_to_metres(1_000.0), 0.0)
        self.assertEqual(build_rjfm_traffic_patterns(), before)
        self.assertTrue(all(not hasattr(spec, "wind") for spec in self.specs))


class TrafficPatternAltitudeTests(unittest.TestCase):
    def test_aiming_marker_distance_rule_uses_2400_m_boundary(self) -> None:
        self.assertEqual(aiming_marker_distance_m(SimpleNamespace(declared_length_m=2_399.9)), 300.0)
        self.assertEqual(aiming_marker_distance_m(SimpleNamespace(declared_length_m=2_400.0)), 400.0)

    def test_aiming_marker_elevation_interpolates_thresholds(self) -> None:
        runway = RJFM.runway("09")
        expected = runway.threshold_elevation_a_ft + 400.0 / runway.measured_length_m * (
            runway.threshold_elevation_b_ft - runway.threshold_elevation_a_ft
        )
        self.assertAlmostEqual(aiming_marker_elevation_ft(runway), expected)

    def test_short_runway_uses_300_m_aiming_marker_in_generated_path(self) -> None:
        original = rjfm_traffic_pattern_specs()[0]
        runway = original.runway
        runway_east, runway_north = runway.runway_unit_vector
        short_runway = replace(
            runway,
            threshold_b=displace_position(
                runway.threshold_a,
                east_m=runway_east * 2_000.0,
                north_m=runway_north * 2_000.0,
            ),
            declared_length_m=2_000.0,
        )
        short_airport = replace(original.airport, runways=(short_runway,))
        path = generate_traffic_pattern(
            replace(original, airport=short_airport, runway=short_runway)
        )
        labels = _labeled_points(path)
        self.assertAlmostEqual(
            distance_m(labels["landing_threshold"].position, labels["aiming_marker"].position),
            300.0,
            delta=0.3,
        )
        self.assertAlmostEqual(
            distance_m(labels["takeoff_aiming_marker"].position, labels["aiming_marker"].position),
            0.0,
            delta=0.01,
        )
        expected_elevation_ft = short_runway.threshold_elevation_a_ft + 300.0 / short_runway.measured_length_m * (
            short_runway.threshold_elevation_b_ft - short_runway.threshold_elevation_a_ft
        )
        self.assertAlmostEqual(
            labels["aiming_marker"].altitude_m,
            feet_to_metres(expected_elevation_ft),
            places=9,
        )
        threshold_to_marker_rise = (
            labels["landing_threshold"].altitude_m - labels["aiming_marker"].altitude_m
        )
        self.assertAlmostEqual(
            threshold_to_marker_rise / 300.0,
            math.tan(math.radians(3.0)),
            places=9,
        )

    def test_descent_starts_with_before_base_turn_and_final_is_three_degrees(self) -> None:
        for spec, path in zip(rjfm_traffic_pattern_specs(), build_rjfm_traffic_patterns(), strict=True):
            points = path.points()
            indices = {point.label: index for index, point in enumerate(points) if point.label}
            descent_start = indices["before_base_turn_start"]
            upwind_turn_start = indices["departure_turn_start"]
            final_end = indices["final_turn_end"]
            threshold = indices["landing_threshold"]
            aiming = indices["aiming_marker"]
            pattern_altitude = feet_to_metres(1_000.0)
            self.assertAlmostEqual(
                points[0].altitude_m,
                feet_to_metres(aiming_marker_elevation_ft(spec.runway)),
            )
            climbing = [point.altitude_m for point in points[: upwind_turn_start + 1]]
            self.assertTrue(all(a <= b for a, b in zip(climbing, climbing[1:])))
            self.assertAlmostEqual(points[upwind_turn_start].altitude_m, pattern_altitude)
            self.assertTrue(
                all(point.altitude_m == pattern_altitude for point in points[upwind_turn_start : descent_start + 1])
            )
            descending = [point.altitude_m for point in points[descent_start : final_end + 1]]
            self.assertTrue(all(a >= b for a, b in zip(descending, descending[1:])))

            labels = _labeled_points(path)
            self.assertAlmostEqual(
                distance_m(labels["landing_threshold"].position, labels["aiming_marker"].position),
                400.0,
                delta=0.3,
            )
            self.assertAlmostEqual(
                points[aiming].altitude_m,
                feet_to_metres(aiming_marker_elevation_ft(spec.runway)),
            )
            rise = points[threshold].altitude_m - points[aiming].altitude_m
            self.assertAlmostEqual(rise / 400.0, math.tan(math.radians(3.0)), places=9)

    def test_complete_circuit_starts_and_finishes_at_the_same_aiming_marker(self) -> None:
        for path in build_rjfm_traffic_patterns():
            start, finish = path.points()[0], path.points()[-1]
            self.assertEqual(start.label, "takeoff_aiming_marker")
            self.assertEqual(finish.label, "aiming_marker")
            self.assertAlmostEqual(distance_m(start.position, finish.position), 0.0, delta=0.01)
            self.assertAlmostEqual(start.altitude_m, finish.altitude_m, places=9)


class ShortDownwindTests(unittest.TestCase):
    def test_task_provided_short_downwind_coordinates_are_unchanged(self) -> None:
        _, short_downwind, _ = build_rjfm_short_downwind_paths()
        self.assertEqual(len(short_downwind.points()), 44)
        for point, (longitude_deg, latitude_deg, altitude_m) in zip(
            short_downwind.points(),
            RJFM_SHORT_DOWNWIND_COORDINATES,
            strict=True,
        ):
            self.assertEqual(point.position.longitude_deg, longitude_deg)
            self.assertEqual(point.position.latitude_deg, latitude_deg)
            self.assertEqual(point.altitude_m, altitude_m)

    def test_task_provided_rwy27_entry_coordinates_are_unchanged(self) -> None:
        entry, _, _ = build_rjfm_short_downwind_paths()
        self.assertEqual(len(entry.points()), 23)
        for point, (longitude_deg, latitude_deg, altitude_m) in zip(
            entry.points(),
            RJFM_SHORT_DOWNWIND_ENTRY_RWY27_COORDINATES,
            strict=True,
        ):
            self.assertEqual(point.position.longitude_deg, longitude_deg)
            self.assertEqual(point.position.latitude_deg, latitude_deg)
            self.assertEqual(point.altitude_m, altitude_m)

    def test_circle_uses_110kt_22deg_radius_and_retains_tangency(self) -> None:
        _, _, circle = build_rjfm_short_downwind_paths()
        spec = rjfm_short_downwind_circle_spec()
        longitude_deg, latitude_deg, altitude_m = RJFM_SHORT_DOWNWIND_CIRCLE_TANGENCY
        tangent = GeoPosition(latitude_deg, longitude_deg)
        normal_east, normal_north = spec.runway.left_normal_unit_vector
        center = displace_position(
            tangent,
            east_m=normal_east * spec.radius_m,
            north_m=normal_north * spec.radius_m,
        )

        self.assertAlmostEqual(spec.true_airspeed_kt, 110.0)
        self.assertAlmostEqual(spec.bank_deg, 22.0)
        self.assertAlmostEqual(spec.radius_m, 808.22466759, places=5)
        self.assertAlmostEqual(distance_m(circle.points()[0].position, tangent), 0.0, delta=0.01)
        self.assertAlmostEqual(
            distance_m(circle.points()[-1].position, tangent),
            0.0,
            delta=0.01,
        )
        for point in circle.points():
            self.assertAlmostEqual(distance_m(center, point.position), spec.radius_m, delta=0.02)
            self.assertEqual(point.altitude_m, altitude_m)

    def test_short_downwind_writer_uses_requested_google_earth_style(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            written = write_rjfm_short_downwind_kmls(directory)
            self.assertEqual(
                {path.name for path in written},
                {
                    RJFM_SHORT_DOWNWIND_FILENAME,
                    RJFM_SHORT_DOWNWIND_CIRCLE_FILENAME,
                    RJFM_SHORT_DOWNWIND_ENTRY_RWY27_FILENAME,
                    RJFM_SHORT_DOWNWIND_COMBINED_FILENAME,
                },
            )
            for path in written:
                root = ET.fromstring(path.read_text(encoding="utf-8"))
                self.assertEqual(root.findtext(".//k:altitudeMode", namespaces=KML_NS), "absolute")
                self.assertEqual(root.findtext(".//k:extrude", namespaces=KML_NS), "1")
                self.assertEqual(root.findtext(".//k:LineStyle/k:width", namespaces=KML_NS), "1")
            entry_root = ET.parse(
                Path(directory) / RJFM_SHORT_DOWNWIND_ENTRY_RWY27_FILENAME
            ).getroot()
            self.assertEqual(
                _style_colors_by_placemark(entry_root),
                {
                    "RJFM Short Downwind Entry RWY27": (
                        RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
                        RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
                    )
                },
            )
            combined_root = ET.parse(
                Path(directory) / RJFM_SHORT_DOWNWIND_COMBINED_FILENAME
            ).getroot()
            combined_colors = _style_colors_by_placemark(combined_root)
            self.assertEqual(
                combined_colors["RJFM Short Downwind Entry RWY27"],
                (
                    RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
                    RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
                ),
            )
            self.assertEqual(
                combined_colors["RJFM Short Downwind"],
                (
                    RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
                    RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
                ),
            )
            self.assertEqual(
                combined_colors["RJFM Circle on Short Downwind"],
                (
                    RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
                    RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
                ),
            )
            standalone_short_root = ET.parse(
                Path(directory) / RJFM_SHORT_DOWNWIND_FILENAME
            ).getroot()
            self.assertEqual(
                _style_colors_by_placemark(standalone_short_root),
                {"RJFM Short Downwind": ("ffffff00", "1affffcc")},
            )


class TrafficPatternKmlTests(unittest.TestCase):
    def test_multi_placemark_kml_contains_all_four_paths(self) -> None:
        paths = build_rjfm_traffic_patterns()
        root = ET.fromstring(reference_paths_to_kml(paths, name="RJFM patterns"))
        placemarks = root.findall(".//k:Placemark", namespaces=KML_NS)
        self.assertEqual(len(placemarks), 4)
        self.assertEqual(
            [placemark.findtext("k:name", namespaces=KML_NS) for placemark in placemarks],
            [path.name for path in paths],
        )

    def test_writer_generates_styled_google_earth_kml_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            written = write_rjfm_traffic_pattern_kmls(directory)
            self.assertEqual(len(written), 5)
            self.assertEqual(
                {path.name for path in written},
                {*RJFM_PATTERN_FILENAMES, RJFM_COMBINED_PATTERN_FILENAME},
            )
            for path in written:
                root = ET.fromstring(path.read_text(encoding="utf-8"))
                self.assertEqual(root.findtext(".//k:altitudeMode", namespaces=KML_NS), "absolute")
                self.assertEqual(root.findtext(".//k:extrude", namespaces=KML_NS), "1")
                self.assertEqual(root.findtext(".//k:LineStyle/k:width", namespaces=KML_NS), "1")
                self.assertEqual(root.findtext(".//k:PolyStyle/k:fill", namespaces=KML_NS), "1")
                self.assertEqual(root.findtext(".//k:PolyStyle/k:outline", namespaces=KML_NS), "0")
                colors = set(_style_colors_by_placemark(root).values())
                expected_style = (
                    RJFM_RWY09_TRAFFIC_PATTERN_STYLE
                    if "RWY09" in path.name
                    else RJFM_RWY27_TRAFFIC_PATTERN_STYLE
                    if "RWY27" in path.name
                    else None
                )
                if expected_style is None:
                    self.assertEqual(
                        colors,
                        {
                            (
                                RJFM_RWY09_TRAFFIC_PATTERN_STYLE.line_color,
                                RJFM_RWY09_TRAFFIC_PATTERN_STYLE.fill_color,
                            ),
                            (
                                RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
                                RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
                            ),
                        },
                    )
                else:
                    self.assertEqual(
                        colors,
                        {(expected_style.line_color, expected_style.fill_color)},
                    )
                placemarks = root.findall(".//k:Placemark", namespaces=KML_NS)
                self.assertEqual(
                    len(placemarks),
                    20 if path.name == RJFM_COMBINED_PATTERN_FILENAME else 5,
                )
                base_names = tuple(
                    placemark.findtext("k:name", namespaces=KML_NS)
                    for placemark in placemarks
                    if "No Circle / No 270" in (
                        placemark.findtext("k:name", namespaces=KML_NS) or ""
                    )
                )
                self.assertEqual(
                    len(base_names),
                    4 if path.name == RJFM_COMBINED_PATTERN_FILENAME else 1,
                )

    def test_writer_emits_circle_without_270_as_separate_placemark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            write_rjfm_traffic_pattern_kmls(
                directory,
                make_circle_before_downwind=True,
                make_circle_middle_downwind=False,
                make_circle_before_base=True,
                make_270_before_downwind=False,
                make_270_before_base=False,
                include_combined=False,
            )
            for filename in RJFM_PATTERN_FILENAMES:
                root = ET.parse(Path(directory) / filename).getroot()
                names = tuple(
                    placemark.findtext("k:name", namespaces=KML_NS)
                    for placemark in root.findall(".//k:Placemark", namespaces=KML_NS)
                )
                self.assertEqual(len(names), 3)
                self.assertTrue(any("Before Downwind Circle" in name for name in names))
                self.assertTrue(any("Before Base Circle" in name for name in names))
                self.assertFalse(any("270" in name and "No 270" not in name for name in names))

    def test_writer_accepts_custom_runway_colors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            write_rjfm_traffic_pattern_kmls(
                directory,
                rwy09_line_color="ff112233",
                rwy09_fill_color="1a445566",
                rwy27_line_color="ff778899",
                rwy27_fill_color="1aaabbcc",
            )
            root = ET.parse(Path(directory) / RJFM_COMBINED_PATTERN_FILENAME).getroot()
            colors = _style_colors_by_placemark(root)
            for name, (line_color, fill_color) in colors.items():
                expected = (
                    ("ff112233", "1a445566")
                    if "RWY09" in name
                    else ("ff778899", "1aaabbcc")
                )
                self.assertEqual((line_color, fill_color), expected)

    def test_writer_keeps_filename_paired_when_spec_order_changes(self) -> None:
        specs = tuple(reversed(rjfm_traffic_pattern_specs()))
        with tempfile.TemporaryDirectory() as directory, patch(
            "sr22_course_simulator.examples.miyazaki_traffic_patterns."
            "rjfm_traffic_pattern_specs",
            return_value=specs,
        ):
            written = write_rjfm_traffic_pattern_kmls(directory, include_combined=False)
            self.assertEqual(
                tuple(path.name for path in written),
                tuple(
                    f"RJFM_RWY{spec.runway.designation}_{spec.label.value.upper()}_MAKE_CIRCLES.kml"
                    for spec in specs
                ),
            )

    def test_multi_placemark_export_rejects_empty_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one placemark"):
            reference_paths_to_kml(())

    def test_multi_placemark_export_supports_one_style_per_path(self) -> None:
        paths = build_rjfm_traffic_patterns()[:2]
        styles = (
            KmlPathStyle(line_color="ff112233", fill_color="1a445566"),
            KmlPathStyle(line_color="ff778899", fill_color="1aaabbcc"),
        )
        root = ET.fromstring(reference_paths_to_kml(paths, styles=styles))
        self.assertEqual(
            list(_style_colors_by_placemark(root).values()),
            [
                ("ff112233", "1a445566"),
                ("ff778899", "1aaabbcc"),
            ],
        )
        with self.assertRaisesRegex(ValueError, "one entry per placemark"):
            reference_paths_to_kml(paths, styles=styles[:1])
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            reference_paths_to_kml(paths, style=styles[0], styles=styles)


if __name__ == "__main__":
    unittest.main()
