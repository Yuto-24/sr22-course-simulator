import hashlib
import json
import math
import unittest
from dataclasses import replace
from itertools import product
from pathlib import Path

from sr22_course_simulator.data.airports import load_airport
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.examples.miyazaki_traffic_patterns import (
    build_rjfm_short_downwind_paths,
    rjfm_traffic_pattern_specs,
)
from sr22_course_simulator.geometry import enu_displacement
from sr22_course_simulator.path import DescentStart, PatternSide, TrafficPatternSpec
from sr22_course_simulator.path.traffic_pattern import (
    generate_traffic_pattern,
    generate_traffic_pattern_components,
)
from sr22_course_simulator.provenance import SourceCitation
from sr22_course_simulator.units import feet_to_metres

SWITCHES = (
    "make_circle_before_downwind",
    "make_270_before_downwind",
    "make_circle_middle_downwind",
    "make_circle_before_base",
    "make_270_before_base",
)


def labels(path):
    return {p.label: p for p in path.points() if p.label}


def local_xy(spec, point):
    east, north = enu_displacement(spec.runway.center_point, point.position)
    ue, un = spec.runway.runway_unit_vector
    ne, nn = (
        spec.runway.left_normal_unit_vector
        if spec.side is PatternSide.LEFT
        else spec.runway.right_normal_unit_vector
    )
    return east * ue + north * un, east * ne + north * nn


def geometry_digest(path):
    # Added abeam vertex lies on the existing straight segment. Compare every
    # pre-existing coordinate at ~0.01 mm horizontal / 1 micrometre altitude.
    values = [
        (
            round(p.position.latitude_deg, 10),
            round(p.position.longitude_deg, 10),
            round(p.altitude_m, 6),
        )
        for p in path.points()
        if p.label != "abeam_threshold"
    ]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def profile(airport, runway, side, descent, **switches):
    # Synthetic test operational values: airport geometry alone comes from AIP.
    return TrafficPatternSpec(
        airport=airport,
        runway=airport.runway(runway),
        side=side,
        altitude_ft=1400,
        downwind_offset_nm=1.5,
        crosswind_base_extension_nm=1.5,
        descent_start=descent,
        source=SourceCitation(document_title="Synthetic profile test"),
        **switches,
    )


class TrafficPatternProfileTests(unittest.TestCase):
    def assert_descent(self, path, start_label, altitude_ft):
        points = path.points()
        indices = {p.label: i for i, p in enumerate(points) if p.label}
        start = indices[start_label]
        climb = indices.get("departure_turn_start", 0)
        for p in points[climb : start + 1]:
            self.assertAlmostEqual(p.altitude_m, feet_to_metres(altitude_ft), places=7)
        # A zero-length semantic alias may follow the turn-end vertex.
        following = next(
            p for p in points[start + 1 :] if p.position != points[start].position
        )
        self.assertLess(following.altitude_m, points[start].altitude_m)
        for a, b in zip(points[start:], points[start + 1 :]):
            self.assertLessEqual(b.altitude_m, a.altitude_m + 1e-8)

    def test_identity_and_operational_values_are_per_direction_and_side(self):
        airport = load_airport("RJFT")
        specs = [
            profile(airport, r.designation, side, DescentStart.BASE_TURN_START)
            for r in airport.runways
            for side in PatternSide
        ]
        self.assertEqual(len({spec.name for spec in specs}), 4)
        for spec in specs:
            self.assertIn(
                f"{airport.icao} RWY{spec.runway.designation} {spec.side.value.upper()}",
                spec.name,
            )
            self.assertFalse(hasattr(spec, "label"))
        changed = replace(
            specs[0],
            altitude_ft=1700,
            descent_start=DescentStart.BASE_TURN_END,
            preferred=True,
            notes=("Synthetic local caution",),
        )
        self.assertEqual(changed.altitude_ft, 1700)
        self.assertEqual(specs[1].altitude_ft, 1400)
        self.assertEqual(changed.name, specs[0].name)
        self.assertTrue(changed.preferred)
        self.assertEqual(changed.notes, ("Synthetic local caution",))
        for kwargs in (
            {"descent_start": "base_turn_start"},
            {"preferred": 1},
            {"notes": "not a tuple"},
            {"notes": (None,)},
        ):
            with self.assertRaises(ValidationError):
                replace(specs[0], **kwargs)

    def test_rjfm_preferred_metadata_preserves_both_sides(self):
        specs = rjfm_traffic_pattern_specs()
        self.assertEqual(len(specs), 4)
        self.assertEqual(
            {(spec.runway.designation, spec.side) for spec in specs if spec.preferred},
            {("09", PatternSide.LEFT), ("27", PatternSide.RIGHT)},
        )
        for spec in specs:
            self.assertIn("北側場周を通常使用", " ".join(spec.source.notes))
            self.assertEqual(
                generate_traffic_pattern_components(spec),
                generate_traffic_pattern_components(
                    replace(spec, preferred=not spec.preferred)
                ),
            )

    def test_three_descent_semantics_across_all_switches_and_directions(self):
        airport = load_airport("RJFO")
        for descent, runway, side, flags in product(
            DescentStart, ("01", "19"), PatternSide, product((False, True), repeat=5)
        ):
            with self.subTest(descent=descent, runway=runway, side=side, flags=flags):
                spec = profile(
                    airport, runway, side, descent, **dict(zip(SWITCHES, flags))
                )
                components = generate_traffic_pattern_components(spec)
                normal = components[0]
                self.assert_descent(normal, descent.value, spec.altitude_ft)
                point = labels(normal)["abeam_threshold"]
                x, y = local_xy(spec, point)
                self.assertAlmostEqual(
                    x, -spec.runway.measured_length_m / 2, delta=1e-6
                )
                self.assertAlmostEqual(y, 1.5 * 1852, delta=1e-6)
                self.assertEqual(len(components), 1 + sum(flags))
                monolithic = generate_traffic_pattern(spec)
                if descent is DescentStart.ABEAM_THRESHOLD:
                    start = "abeam_threshold"
                elif descent is DescentStart.BASE_TURN_END:
                    start = (
                        "before_base_turn_end"
                        if spec.make_270_before_base
                        else "base_turn_end"
                    )
                else:
                    start = (
                        "before_base_turn_start"
                        if spec.make_270_before_base
                        else "before_base_turn_end"
                        if spec.make_circle_before_base
                        else "base_turn_start"
                    )
                self.assert_descent(monolithic, start, spec.altitude_ft)
                if flags[-1]:
                    alternative = components[-1]
                    if descent is DescentStart.BASE_TURN_END:
                        self.assert_descent(
                            alternative, "before_base_turn_end", spec.altitude_ft
                        )
                        self.assertEqual(
                            alternative.points()[-1].position,
                            labels(normal)["final_turn_end"].position,
                        )
                        self.assertAlmostEqual(
                            alternative.points()[-1].altitude_m,
                            labels(normal)["final_turn_end"].altitude_m,
                            places=7,
                        )
                    elif descent is DescentStart.ABEAM_THRESHOLD:
                        self.assertEqual(
                            alternative.points()[0].position,
                            labels(normal)["base_turn_start"].position,
                        )
                        self.assertAlmostEqual(
                            alternative.points()[0].altitude_m,
                            labels(normal)["base_turn_start"].altitude_m,
                            places=7,
                        )
                        self.assertAlmostEqual(
                            alternative.points()[-1].altitude_m,
                            labels(normal)["base_turn_end"].altitude_m,
                            places=7,
                        )
                        self.assertLess(
                            alternative.points()[-1].altitude_m,
                            alternative.points()[0].altitude_m,
                        )
                final = labels(normal)
                aiming_x, _ = local_xy(spec, final["aiming_marker"])
                for label in ("landing_threshold", "final_turn_end"):
                    x, _ = local_xy(spec, final[label])
                    expected = final["aiming_marker"].altitude_m + (
                        aiming_x - x
                    ) * math.tan(math.radians(3))
                    self.assertAlmostEqual(
                        final[label].altitude_m, expected, delta=1e-6
                    )

    def test_base_and_each_component_remain_identical_when_other_switches_change(self):
        for descent in DescentStart:
            spec = profile(
                load_airport("RJFO"),
                "01",
                PatternSide.LEFT,
                descent,
                **dict.fromkeys(SWITCHES, True),
            )
            expected = {p.name: p for p in generate_traffic_pattern_components(spec)}
            for flags in product((False, True), repeat=5):
                for path in generate_traffic_pattern_components(
                    replace(spec, **dict(zip(SWITCHES, flags)))
                ):
                    self.assertEqual(path, expected[path.name])

    def test_abeam_at_straight_downwind_endpoint_keeps_both_semantic_labels(self):
        airport = load_airport("RJFO")
        spec = profile(
            airport,
            "01",
            PatternSide.LEFT,
            DescentStart.ABEAM_THRESHOLD,
            **dict.fromkeys(SWITCHES, False),
        )
        normal = generate_traffic_pattern(spec)
        base_x, _ = local_xy(spec, labels(normal)["base_turn_start"])
        # Solve the extension that places Base entry exactly at abeam.
        extension = (
            spec.crosswind_base_extension_nm
            + (base_x + spec.runway.measured_length_m / 2) / 1852
        )
        boundary = generate_traffic_pattern(
            replace(spec, crosswind_base_extension_nm=extension)
        )
        semantic = labels(boundary)
        self.assertAlmostEqual(
            local_xy(spec, semantic["abeam_threshold"])[0],
            local_xy(spec, semantic["base_turn_start"])[0],
            delta=1e-6,
        )
        self.assert_descent(boundary, "abeam_threshold", spec.altitude_ft)

    def test_missing_abeam_straight_reports_the_required_relationship(self):
        spec = profile(
            load_airport("RJFO"),
            "01",
            PatternSide.LEFT,
            DescentStart.ABEAM_THRESHOLD,
            **dict.fromkeys(SWITCHES, False),
        )
        with self.assertRaisesRegex(
            ValidationError, "model gap.*straight Downwind.*landing-threshold"
        ):
            generate_traffic_pattern(replace(spec, crosswind_base_extension_nm=0.1))

    def test_rjfm_pr7_geometry_all_32_combinations_and_short_downwind(self):
        expected = json.loads(
            (Path(__file__).parent / "fixtures/rjfm_pr7_geometry.json").read_text()
        )
        for flags in product((False, True), repeat=5):
            for spec in rjfm_traffic_pattern_specs(**dict(zip(SWITCHES, flags))):
                key = f"{spec.runway.designation}_{spec.side.value}_" + "".join(
                    str(int(x)) for x in flags
                )
                with self.subTest(key=key):
                    actual = [
                        geometry_digest(generate_traffic_pattern(spec)),
                        *[
                            geometry_digest(p)
                            for p in generate_traffic_pattern_components(spec)
                        ],
                    ]
                    self.assertEqual(actual, expected[key])
        self.assertEqual(
            [geometry_digest(p) for p in build_rjfm_short_downwind_paths()],
            expected["short_downwind"],
        )
