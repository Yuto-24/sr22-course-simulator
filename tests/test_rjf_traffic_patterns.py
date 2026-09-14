"""Issue #9 acceptance tests against operational values and geometric invariants."""

from dataclasses import replace
from itertools import product
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from sr22_course_simulator.aircraft import GeoPosition
from sr22_course_simulator.data.airports import load_airport
from sr22_course_simulator.data.airports.traffic_profiles import (
    RJF_AIRPORTS,
    generic_pattern_altitude_ft,
    rjf_traffic_pattern_specs,
)
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.examples.rjf_traffic_patterns import (
    build_rjf_traffic_patterns,
    pattern_identity,
    write_rjf_traffic_pattern_kmls,
)
from sr22_course_simulator.export import reference_paths_to_kml
from sr22_course_simulator.geometry import enu_displacement
from sr22_course_simulator.path import DescentStart, PatternSide
from sr22_course_simulator.path.traffic_pattern import (
    generate_traffic_pattern_components,
)
from sr22_course_simulator.units import feet_to_metres

SWITCHES = (
    "make_circle_before_downwind",
    "make_270_before_downwind",
    "make_circle_middle_downwind",
    "make_circle_before_base",
    "make_270_before_base",
)
# Explicit acceptance oracle, independent of production table iteration/order.
EXPECTED = {
    "RJFS": ("11", "29", (1000, 1000, 1000, 1000), (False, True, True, False)),
    "RJFO": ("01", "19", (1300, 1000, 1000, 1300), (False, True, True, False)),
    "RJFK": ("16", "34", (1900, 1900, 1900, 1900), (False,) * 4),
    "RJFT": ("07", "25", (1400, 1700, 1700, 1400), (False,) * 4),
    "RJFG": ("13", "31", (1800, 1800, 1800, 1800), (True, False, False, True)),
    "RJFU": ("14", "32", (1000, 1000, 1000, 1000), (False,) * 4),
    "RJFC": ("14", "32", (1100, 1100, 1100, 1100), (False,) * 4),
}
NS = {"k": "http://www.opengis.net/kml/2.2"}


def labels(path):
    return {p.label: p for p in path.points() if p.label}


def xy(spec, point):
    east, north = enu_displacement(spec.runway.center_point, point.position)
    u = spec.runway.runway_unit_vector
    n = (
        spec.runway.left_normal_unit_vector
        if spec.side is PatternSide.LEFT
        else spec.runway.right_normal_unit_vector
    )
    return east * u[0] + north * u[1], east * n[0] + north * n[1]


class RjfTrafficPatternTests(unittest.TestCase):
    def assert_descent(self, path, label, altitude_ft):
        points = path.points()
        indices = {p.label: i for i, p in enumerate(points) if p.label}
        start = indices[label]
        for point in points[indices.get("departure_turn_start", 0) : start + 1]:
            self.assertAlmostEqual(
                point.altitude_m, feet_to_metres(altitude_ft), places=7
            )
        # Semantic aliases can differ by sub-nanometre roundoff across Python
        # versions; only a spatially distinct next point must be lower.
        following = next(
            p
            for p in points[start + 1 :]
            if math.hypot(*enu_displacement(p.position, points[start].position)) > 1e-6
        )
        self.assertLess(following.altitude_m, points[start].altitude_m)
        for a, b in zip(points[start:], points[start + 1 :]):
            self.assertLessEqual(b.altitude_m, a.altitude_m + 1e-8)

    def test_all_28_profiles_match_source_matrix(self):
        self.assertEqual(set(RJF_AIRPORTS), set(EXPECTED))
        identities = set()
        for icao, (r1, r2, altitudes, preferred) in EXPECTED.items():
            specs = rjf_traffic_pattern_specs(icao)
            self.assertEqual(len(specs), 4)
            expected_keys = tuple(product((r1, r2), PatternSide))
            self.assertEqual(
                tuple((s.runway.designation, s.side) for s in specs), expected_keys
            )
            self.assertEqual(tuple(s.altitude_ft for s in specs), altitudes)
            self.assertEqual(tuple(s.preferred for s in specs), preferred)
            for index, spec in enumerate(specs):
                with self.subTest(identity=pattern_identity(spec)):
                    identities.add(pattern_identity(spec))
                    descent = (
                        DescentStart.ABEAM_THRESHOLD
                        if icao == "RJFO" and index in (0, 3)
                        else DescentStart.BASE_TURN_END
                        if icao == "RJFT" and index in (0, 3)
                        else DescentStart.BASE_TURN_START
                    )
                    self.assertIs(spec.descent_start, descent)
                    self.assertEqual(
                        (spec.downwind_offset_nm, spec.crosswind_base_extension_nm),
                        (1.5, 1.5),
                    )
                    self.assertEqual(
                        (
                            spec.true_airspeed_kt,
                            spec.normal_bank_deg,
                            spec.downwind_turn_bank_deg,
                            spec.base_turn_bank_deg,
                            spec.final_bank_deg,
                            spec.roll_rate_deg_s,
                            spec.glide_path_deg,
                        ),
                        (110, 30, 22, 22, 25, 10, 3),
                    )
                    self.assertEqual(spec.airport, load_airport(icao))
                    self.assertEqual(
                        spec.runway, load_airport(icao).runway(spec.runway.designation)
                    )
        self.assertEqual(len(identities), 28)

    def test_rounding_and_generic_vs_local_provenance(self):
        for elevation, expected in (
            (49, 1000),
            (50, 1100),
            (150, 1200),
            (311, 1300),
            (891, 1900),
            (8, 1000),
            (122, 1100),
        ):
            self.assertEqual(generic_pattern_altitude_ft(elevation), expected)
        for icao in RJF_AIRPORTS:
            for spec in rjf_traffic_pattern_specs(icao):
                generic = icao in ("RJFK", "RJFU", "RJFC") or (
                    icao == "RJFO" and spec.preferred
                )
                self.assertIn(
                    "generic_field_plus_1000" if generic else "local_explicit",
                    spec.notes[0],
                )
                self.assertIn("issues/9", spec.source.extraction_method)
                for source in (spec.airport.source, spec.runway.source):
                    self.assertTrue(source.effective_date)
                    self.assertTrue(source.section)
                    self.assertIn(source.document_title, " ".join(spec.source.notes))
        changed = replace(load_airport("RJFK"), elevation_ft=950)
        with patch(
            "sr22_course_simulator.data.airports.traffic_profiles.load_airport",
            return_value=changed,
        ):
            self.assertEqual(
                {s.altitude_ft for s in rjf_traffic_pattern_specs("RJFK")}, {2000}
            )
        self.assertIn(
            "explicitly overrides", " ".join(rjf_traffic_pattern_specs("RJFT")[1].notes)
        )
        self.assertIn("not a VFR", " ".join(rjf_traffic_pattern_specs("RJFC")[0].notes))

    def test_reciprocal_physical_side_mapping_and_preference(self):
        for icao in RJF_AIRPORTS:
            specs = rjf_traffic_pattern_specs(icao)
            for first, reciprocal in ((specs[0], specs[3]), (specs[1], specs[2])):
                a = (
                    first.runway.left_normal_unit_vector
                    if first.side is PatternSide.LEFT
                    else first.runway.right_normal_unit_vector
                )
                b = (
                    reciprocal.runway.left_normal_unit_vector
                    if reciprocal.side is PatternSide.LEFT
                    else reciprocal.runway.right_normal_unit_vector
                )
                self.assertAlmostEqual(a[0], b[0], places=12)
                self.assertAlmostEqual(a[1], b[1], places=12)
                self.assertEqual(
                    first.runway.threshold_a, reciprocal.runway.threshold_b
                )
                self.assertEqual(
                    first.runway.center_point, reciprocal.runway.center_point
                )
                self.assertEqual(first.altitude_ft, reciprocal.altitude_ft)
                self.assertEqual(first.descent_start, reciprocal.descent_start)
                self.assertEqual(first.preferred, reciprocal.preferred)
            for spec in specs:
                n = (
                    spec.runway.left_normal_unit_vector
                    if spec.side is PatternSide.LEFT
                    else spec.runway.right_normal_unit_vector
                )
                if icao == "RJFS":
                    self.assertEqual(spec.preferred, n[1] < 0)  # physical south
                elif icao == "RJFG":
                    self.assertEqual(spec.preferred, n[1] > 0)  # physical north
                elif icao == "RJFO":
                    self.assertEqual(spec.preferred, n[0] > 0)  # physical east
                elif icao == "RJFT":
                    self.assertEqual(spec.altitude_ft, 1400 if n[1] > 0 else 1700)

    def test_all_896_flag_combinations_preserve_components_and_altitude_semantics(self):
        for icao in RJF_AIRPORTS:
            all_pairs = build_rjf_traffic_patterns(
                icao, **dict.fromkeys(SWITCHES, True)
            )
            expected = {
                pattern_identity(s): {p.name: p for p in paths}
                for s, paths in all_pairs
            }
            for flags in product((False, True), repeat=5):
                for spec, paths in build_rjf_traffic_patterns(
                    icao, **dict(zip(SWITCHES, flags))
                ):
                    with self.subTest(identity=pattern_identity(spec), flags=flags):
                        self.assertEqual(len(paths), 1 + sum(flags))
                        for path in paths:
                            self.assertEqual(
                                path, expected[pattern_identity(spec)][path.name]
                            )
                        normal = paths[0]
                        self.assert_descent(
                            normal, spec.descent_start.value, spec.altitude_ft
                        )
                        if flags[-1]:
                            alternative = paths[-1]
                            normal_labels = labels(normal)
                            if spec.descent_start is DescentStart.BASE_TURN_END:
                                self.assert_descent(
                                    alternative,
                                    "before_base_turn_end",
                                    spec.altitude_ft,
                                )
                                merge = normal_labels["final_turn_end"]
                            else:
                                merge = normal_labels["base_turn_end"]
                            # Independently transformed tangent endpoints differ at
                            # floating-point roundoff; require sub-micrometre closure.
                            self.assertLess(
                                math.hypot(
                                    *enu_displacement(
                                        alternative.points()[-1].position,
                                        merge.position,
                                    )
                                ),
                                1e-6,
                            )
                            self.assertAlmostEqual(
                                alternative.points()[-1].altitude_m,
                                merge.altitude_m,
                                places=7,
                            )
                            if spec.descent_start is DescentStart.ABEAM_THRESHOLD:
                                self.assertLess(
                                    alternative.points()[0].altitude_m,
                                    feet_to_metres(spec.altitude_ft),
                                )
                                self.assertAlmostEqual(
                                    alternative.points()[0].altitude_m,
                                    normal_labels["base_turn_start"].altitude_m,
                                    places=7,
                                )

    def test_axes_abeam_and_continuous_three_degree_final_all_patterns(self):
        for icao in RJF_AIRPORTS:
            for spec, paths in build_rjf_traffic_patterns(icao):
                p = labels(paths[0])
                half = spec.runway.measured_length_m / 2
                for label in ("departure_turn_end", "downwind_turn_start"):
                    self.assertAlmostEqual(
                        xy(spec, p[label])[0], half + 1.5 * 1852, delta=1e-6
                    )
                for label in ("base_turn_end", "final_turn_start"):
                    self.assertAlmostEqual(
                        xy(spec, p[label])[0], -half - 1.5 * 1852, delta=1e-6
                    )
                for label in (
                    "downwind_turn_end",
                    "abeam_threshold",
                    "base_turn_start",
                ):
                    self.assertAlmostEqual(
                        xy(spec, p[label])[1], 1.5 * 1852, delta=1e-6
                    )
                self.assertAlmostEqual(
                    xy(spec, p["abeam_threshold"])[0], -half, delta=1e-6
                )
                self.assert_descent(
                    paths[0], spec.descent_start.value, spec.altitude_ft
                )
                aiming_x, _ = xy(spec, p["aiming_marker"])
                start = paths[0].points().index(p["final_turn_end"])
                for point in paths[0].points()[start:]:
                    x, y = xy(spec, point)
                    self.assertAlmostEqual(y, 0, delta=1e-6)
                    self.assertAlmostEqual(
                        point.altitude_m,
                        p["aiming_marker"].altitude_m
                        + (aiming_x - x) * math.tan(math.radians(3)),
                        delta=1e-6,
                    )
                # Metadata and ARP/magnetic data cannot change the ReferencePath.
                changed_airport = replace(
                    spec.airport,
                    reference_point=GeoPosition(0, 0),
                    magnetic_variation_deg=0,
                )
                self.assertEqual(
                    generate_traffic_pattern_components(spec),
                    generate_traffic_pattern_components(
                        replace(
                            spec, airport=changed_airport, preferred=not spec.preferred
                        )
                    ),
                )

    def test_35_kml_files_coordinates_components_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            all_files = []
            for icao in RJF_AIRPORTS:
                switches = dict.fromkeys(SWITCHES, True)
                pairs = build_rjf_traffic_patterns(icao, **switches)
                files = write_rjf_traffic_pattern_kmls(directory, icao, **switches)
                self.assertEqual(len(files), 5)
                all_files.extend(files)
                groups = [((spec, paths),) for spec, paths in pairs] + [pairs]
                for file, group in zip(files, groups, strict=True):
                    tree = ET.fromstring(file.read_text())
                    placemarks = tree.findall(".//k:Placemark", NS)
                    expected = [(spec, p) for spec, paths in group for p in paths]
                    self.assertEqual(len(placemarks), len(expected))
                    for pm, (spec, path) in zip(placemarks, expected, strict=True):
                        self.assertEqual(
                            pm.findtext("k:name", namespaces=NS), path.name
                        )
                        self.assertTrue(path.name.startswith(pattern_identity(spec)))
                        self.assertEqual(
                            pm.findtext("k:LineString/k:altitudeMode", namespaces=NS),
                            "absolute",
                        )
                        metadata = json.loads(
                            pm.findtext("k:description", namespaces=NS)
                        )
                        self.assertEqual(metadata["preferred"], spec.preferred)
                        self.assertEqual(metadata["altitude_ft_msl"], spec.altitude_ft)
                        self.assertEqual(
                            metadata["descent_start"], spec.descent_start.value
                        )
                        self.assertEqual(
                            metadata["runway_source"]["effective_date"],
                            spec.runway.source.effective_date,
                        )
                        coordinates = [
                            tuple(map(float, item.split(",")))
                            for item in pm.findtext(
                                "k:LineString/k:coordinates", namespaces=NS
                            ).split()
                        ]
                        self.assertEqual(len(coordinates), len(path.points()))
                        for actual, point in zip(
                            coordinates, path.points(), strict=True
                        ):
                            self.assertAlmostEqual(
                                actual[0], point.position.longitude_deg, delta=1e-8
                            )
                            self.assertAlmostEqual(
                                actual[1], point.position.latitude_deg, delta=1e-8
                            )
                            self.assertAlmostEqual(
                                actual[2], point.altitude_m, delta=1e-7
                            )
            self.assertEqual(len(set(all_files)), 35)
            self.assertEqual(len(list(Path(directory).glob("*.kml"))), 35)

    def test_cli_selects_airport_and_independent_booleans(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "sr22_course_simulator.examples.rjf_traffic_patterns",
                    "--airport",
                    "RJFT",
                    "--output-dir",
                    directory,
                    *[f"--no-{flag.replace('_', '-')}" for flag in SWITCHES],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(len(result.stdout.splitlines()), 5)
            tree = ET.parse(Path(directory) / "RJFT_ALL_TRAFFIC_PATTERNS.kml")
            self.assertEqual(len(tree.findall(".//k:Placemark", NS)), 4)

    def test_unsupported_profiles_and_invalid_switches_are_explicit(self):
        for icao in ("RJFE", "RJFM", "", None):
            with self.assertRaisesRegex(
                ValidationError, "model gap.*operational profile"
            ):
                rjf_traffic_pattern_specs(icao)
        with self.assertRaisesRegex(ValidationError, "must be bool"):
            rjf_traffic_pattern_specs("RJFO", make_270_before_base=1)
        self.assertEqual(
            rjf_traffic_pattern_specs(" rjfo "), rjf_traffic_pattern_specs("RJFO")
        )

    def test_kml_description_count_and_xml_escaping(self):
        path = build_rjf_traffic_patterns("RJFS")[0][1][0]
        with self.assertRaisesRegex(ValueError, "descriptions must contain one entry"):
            reference_paths_to_kml((path,), descriptions=())
        description = 'source <table> & "local"'
        tree = ET.fromstring(
            reference_paths_to_kml((path,), descriptions=(description,))
        )
        self.assertEqual(tree.findtext(".//k:description", namespaces=NS), description)
        self.assertIsNone(
            ET.fromstring(reference_paths_to_kml((path,))).find(".//k:description", NS)
        )
