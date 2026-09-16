"""Issue #13 acceptance tests for the all-Kyushu traffic-pattern export."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from sr22_course_simulator.data.airports.traffic_profiles import RJF_AIRPORTS
from sr22_course_simulator.examples.kyushu_traffic_patterns import (
    KYUSHU_AIRPORTS,
    build_kyushu_traffic_patterns,
    write_kyushu_traffic_pattern_exports,
)
from sr22_course_simulator.examples.rjf_traffic_patterns import (
    pattern_identity,
)
from sr22_course_simulator.examples.miyazaki_traffic_patterns import (
    rjfm_traffic_pattern_specs,
)
from sr22_course_simulator.path.traffic_pattern import generate_traffic_pattern_components


NS = {"k": "http://www.opengis.net/kml/2.2"}
SWITCHES = (
    "make_circle_before_downwind",
    "make_270_before_downwind",
    "make_circle_middle_downwind",
    "make_circle_before_base",
    "make_270_before_base",
)
EXPECTED_KYUSHU_AIRPORTS = (
    "RJFM", "RJFS", "RJFO", "RJFK", "RJFT", "RJFG", "RJFU", "RJFC",
)


def _identity(spec) -> str:
    return pattern_identity(spec)


def _placemarks(root: ET.Element) -> dict[str, ET.Element]:
    return {
        p.findtext("k:name", namespaces=NS): p
        for p in root.findall(".//k:Placemark", namespaces=NS)
    }


def _coordinates(placemark: ET.Element) -> tuple[str, ...]:
    text = placemark.findtext("k:LineString/k:coordinates", namespaces=NS) or ""
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def _description(placemark: ET.Element) -> str:
    return placemark.findtext("k:description", namespaces=NS) or ""


def _altitude_mode(placemark: ET.Element) -> str | None:
    return placemark.findtext("k:LineString/k:altitudeMode", namespaces=NS)


def _numeric_coordinates(placemark: ET.Element) -> tuple[tuple[float, float, float], ...]:
    return tuple(tuple(float(value) for value in item.split(",")) for item in _coordinates(placemark))


def _read_kmz(path: Path) -> ET.Element:
    with ZipFile(path) as archive:
        assert archive.namelist() == ["doc.kml"]
        return ET.fromstring(archive.read("doc.kml"))


def _source_json(value) -> object:
    return json.loads(json.dumps(asdict(value)))


class KyushuTrafficPatternTests(unittest.TestCase):
    def test_airport_matrix_has_eight_airports_and_all_32_identities(self) -> None:
        self.assertEqual(KYUSHU_AIRPORTS, EXPECTED_KYUSHU_AIRPORTS)
        self.assertEqual(KYUSHU_AIRPORTS[1:], tuple(RJF_AIRPORTS))
        pairs = tuple(
            pair for icao in KYUSHU_AIRPORTS
            for pair in build_kyushu_traffic_patterns(icao, **dict.fromkeys(SWITCHES, False))
        )
        self.assertEqual(len(pairs), 32)
        identities = {_identity(spec) for spec, _ in pairs}
        self.assertEqual(len(identities), 32)
        for icao in KYUSHU_AIRPORTS:
            airport_identities = {identity for identity in identities if identity.startswith(f"{icao}_")}
            self.assertEqual(len(airport_identities), 4)

    def test_each_switch_is_independent_and_preserves_normal_geometry(self) -> None:
        for icao in KYUSHU_AIRPORTS:
            baseline = dict(
                (_identity(spec), paths)
                for spec, paths in build_kyushu_traffic_patterns(
                    icao, **dict.fromkeys(SWITCHES, False)
                )
            )
            for switch in SWITCHES:
                flags = {name: name == switch for name in SWITCHES}
                for spec, paths in build_kyushu_traffic_patterns(icao, **flags):
                    with self.subTest(icao=icao, switch=switch, identity=_identity(spec)):
                        self.assertEqual(len(paths), 2)
                        self.assertEqual(paths[0], baseline[_identity(spec)][0])
                        self.assertNotEqual(paths[1].name, paths[0].name)
            all_on = dict.fromkeys(SWITCHES, True)
            for spec, paths in build_kyushu_traffic_patterns(icao, **all_on):
                self.assertEqual(len(paths), 6)
                self.assertEqual(paths[0], baseline[_identity(spec)][0])

    def test_rjfm_matches_existing_specs_and_components(self) -> None:
        switches = dict.fromkeys(SWITCHES, False)
        expected_specs = rjfm_traffic_pattern_specs(**switches)
        actual = build_kyushu_traffic_patterns("RJFM", **switches)
        self.assertEqual(tuple(_identity(s) for s, _ in actual), tuple(_identity(s) for s in expected_specs))
        for (actual_spec, actual_paths), expected_spec in zip(actual, expected_specs, strict=True):
            expected_paths = tuple(
                replace(path, name=f"{_identity(expected_spec)} {path.name.removeprefix(prefix)}")
                for path in generate_traffic_pattern_components(expected_spec)
                for prefix in (f"RJFM RWY{expected_spec.runway.designation} {expected_spec.side.value.upper()} ",)
            )
            self.assertEqual(actual_spec, expected_spec)
            self.assertEqual(actual_paths, expected_paths)

    def test_selected_export_has_raw_files_and_kmz(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            written = write_kyushu_traffic_pattern_exports(directory, "RJFM", **dict.fromkeys(SWITCHES, False))
            self.assertEqual(len(written), 6)
            self.assertEqual({p.suffix for p in written}, {".kml", ".kmz"})
            self.assertEqual(sum(p.suffix == ".kml" for p in written), 5)
            kmz = next(p for p in written if p.suffix == ".kmz")
            with ZipFile(kmz) as archive:
                self.assertEqual(archive.namelist(), ["doc.kml"])
                root = ET.fromstring(archive.read("doc.kml"))
            folders = {f.findtext("k:name", namespaces=NS) for f in root.findall(".//k:Folder", namespaces=NS)}
            self.assertIn("RJFM", folders)
            self.assertIn("RWY09", folders)
            self.assertIn("RWY27", folders)
            self.assertIn("LEFT", folders)
            self.assertIn("RIGHT", folders)

    def test_all_switches_on_kmz_matches_source_paths_and_metadata(self) -> None:
        switches = dict.fromkeys(SWITCHES, True)
        with tempfile.TemporaryDirectory() as directory:
            written = write_kyushu_traffic_pattern_exports(directory, **switches)
            self.assertEqual(len(written), 49)
            kmz = Path(directory) / "KYUSHU_TRAFFIC_PATTERNS.kmz"
            self.assertIn(kmz, written)
            root = _read_kmz(kmz)
            bundled = _placemarks(root)
            self.assertEqual(len(bundled), 192)
            raw = {}
            for path in written:
                if path.suffix == ".kml":
                    raw.update(_placemarks(ET.parse(path).getroot()))
            self.assertEqual(set(raw), set(bundled))
            style_ids = {f"#{s.attrib['id']}" for s in root.findall(".//k:Style", namespaces=NS)}
            expected_paths = {}
            expected_specs = {}
            for icao in KYUSHU_AIRPORTS:
                for spec, paths in build_kyushu_traffic_patterns(icao, **switches):
                    for path in paths:
                        expected_paths[path.name] = path
                        expected_specs[path.name] = spec
            self.assertEqual(set(bundled), set(expected_paths))
            for name, placemark in bundled.items():
                with self.subTest(name=name):
                    path = expected_paths[name]
                    spec = expected_specs[name]
                    expected_coordinates = tuple(
                        (point.position.longitude_deg, point.position.latitude_deg, point.altitude_m)
                        for point in path.points()
                    )
                    self.assertEqual(_coordinates(placemark), _coordinates(raw[name]))
                    self.assertEqual(_description(placemark), _description(raw[name]))
                    for actual, expected in zip(_numeric_coordinates(placemark), expected_coordinates, strict=True):
                        self.assertEqual(len(actual), 3)
                        self.assertAlmostEqual(actual[0], expected[0], delta=1e-8)
                        self.assertAlmostEqual(actual[1], expected[1], delta=1e-8)
                        self.assertAlmostEqual(actual[2], expected[2], delta=1e-7)
                    self.assertEqual(_altitude_mode(placemark), "absolute")
                    self.assertIn(placemark.findtext("k:styleUrl", namespaces=NS), style_ids)
                    metadata = json.loads(_description(placemark))
                    self.assertEqual(metadata["identity"], _identity(spec))
                    self.assertEqual(metadata["preferred"], spec.preferred)
                    self.assertEqual(metadata["altitude_ft_msl"], spec.altitude_ft)
                    self.assertEqual(metadata["descent_start"], spec.descent_start.value)
                    self.assertEqual(metadata["notes"], list(spec.notes))
                    self.assertEqual(metadata["operational_source"], _source_json(spec.source))
                    self.assertEqual(metadata["airport_source"], _source_json(spec.airport.source))
                    self.assertEqual(metadata["runway_source"], _source_json(spec.runway.source))

            for icao in KYUSHU_AIRPORTS[1:]:
                self.assertEqual(
                    json.loads(_description(next(p for n, p in bundled.items() if n.startswith(f"{icao}_"))))["source_snapshot"]["information_baseline"],
                    "2026-09-03 AIRAC AMDT",
                )
            rjfm_metadata = json.loads(
                _description(next(p for n, p in bundled.items() if n.startswith("RJFM_")))
            )
            self.assertNotIn("source_snapshot", rjfm_metadata)

    def test_each_airport_kmz_has_complete_hierarchy_and_six_components_per_side(self) -> None:
        switches = dict.fromkeys(SWITCHES, True)
        with tempfile.TemporaryDirectory() as directory:
            written = write_kyushu_traffic_pattern_exports(directory, **switches)
            for icao in KYUSHU_AIRPORTS:
                root = _read_kmz(Path(directory) / f"{icao}_TRAFFIC_PATTERNS.kmz")
                airport = next(
                    folder for folder in root.findall(".//k:Folder", namespaces=NS)
                    if folder.findtext("k:name", namespaces=NS) == icao
                )
                pairs = build_kyushu_traffic_patterns(icao, **switches)
                self.assertEqual(len(airport.findall("k:Folder", namespaces=NS)), 2)
                for spec, paths in pairs:
                    runway = next(
                        folder for folder in airport.findall("k:Folder", namespaces=NS)
                        if folder.findtext("k:name", namespaces=NS) == f"RWY{spec.runway.designation}"
                    )
                    side = next(
                        folder for folder in runway.findall("k:Folder", namespaces=NS)
                        if folder.findtext("k:name", namespaces=NS) == spec.side.value.upper()
                    )
                    self.assertEqual(len(side.findall("k:Placemark", namespaces=NS)), 6)
                    self.assertEqual(
                        {p.findtext("k:name", namespaces=NS) for p in side.findall("k:Placemark", namespaces=NS)},
                        {path.name for path in paths},
                    )
                    style_ids = {f"#{s.attrib['id']}" for s in root.findall(".//k:Style", namespaces=NS)}
                    for placemark in side.findall("k:Placemark", namespaces=NS):
                        self.assertIn(placemark.findtext("k:styleUrl", namespaces=NS), style_ids)
                        self.assertEqual(_altitude_mode(placemark), "absolute")


if __name__ == "__main__":
    unittest.main()
