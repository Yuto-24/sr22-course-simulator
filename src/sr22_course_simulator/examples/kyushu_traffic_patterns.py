"""Jupyter-oriented KML and KMZ exports for RJFM plus seven Issue #9 airports."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from sr22_course_simulator.data.airports.traffic_profiles import (
    RJF_AIRPORTS,
)
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.examples.miyazaki_traffic_patterns import (
    rjfm_traffic_pattern_specs,
)
from sr22_course_simulator.examples.rjf_traffic_patterns import (
    build_rjf_traffic_patterns,
    pattern_description,
    pattern_identity,
)
from sr22_course_simulator.export import (
    GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
    reference_paths_to_kml,
    write_kml,
    write_kmz,
)
from sr22_course_simulator.export.kml import KML_NAMESPACE
from sr22_course_simulator.path import PolylineReferencePath, TrafficPatternSpec
from sr22_course_simulator.path.traffic_pattern import generate_traffic_pattern_components


KYUSHU_AIRPORTS = ("RJFM", *RJF_AIRPORTS)
SOURCE_SNAPSHOT = {
    "information_baseline": "2026-09-03 AIRAC AMDT",
    "applicable_airports": RJF_AIRPORTS,
}
_KML = f"{{{KML_NAMESPACE}}}"


def _normalise_icao(icao: str) -> str:
    if not isinstance(icao, str) or icao.strip().upper() not in KYUSHU_AIRPORTS:
        raise ValidationError(
            f"model gap: {icao!r} has no Issue #9 traffic-pattern profile"
        )
    return icao.strip().upper()


def build_kyushu_traffic_patterns(
    icao: str,
    **switches: bool,
) -> tuple[tuple[TrafficPatternSpec, tuple[PolylineReferencePath, ...]], ...]:
    """Return four existing specs paired with their selected components.

    RJFM retains its specialized source-backed specifications and components.
    The other seven airports delegate to the existing Issue #9 builder.  All
    geometry comes from those shared implementations.
    """

    airport = _normalise_icao(icao)
    if airport != "RJFM":
        return build_rjf_traffic_patterns(airport, **switches)
    pairs = []
    for spec in rjfm_traffic_pattern_specs(**switches):
        prefix = f"{spec.airport.icao} RWY{spec.runway.designation} {spec.side.value.upper()} "
        components = tuple(
            replace(path, name=f"{pattern_identity(spec)} {path.name.removeprefix(prefix)}")
            for path in generate_traffic_pattern_components(spec)
        )
        pairs.append((spec, components))
    return tuple(pairs)


def _description(spec: TrafficPatternSpec) -> str:
    """Add the Issue #9 snapshot without changing source effective dates."""

    metadata = json.loads(pattern_description(spec))
    if spec.airport.icao in RJF_AIRPORTS:
        metadata["source_snapshot"] = SOURCE_SNAPSHOT
    return json.dumps(metadata, ensure_ascii=False, indent=2)


def _folder(parent: ET.Element, name: str) -> ET.Element:
    folder = ET.SubElement(parent, f"{_KML}Folder")
    ET.SubElement(folder, f"{_KML}name").text = name
    return folder


def _foldered_kml(
    airport_pairs: tuple[
        tuple[str, tuple[tuple[TrafficPatternSpec, tuple[PolylineReferencePath, ...]], ...]],
        ...,
    ],
    *,
    name: str,
) -> str:
    """Use the normal KML exporter, then group its Placemarks for Google Earth."""

    ordered = tuple(
        (icao, spec, path)
        for icao, pairs in airport_pairs
        for spec, paths in pairs
        for path in paths
    )
    kml = reference_paths_to_kml(
        (path for _, _, path in ordered),
        name=name,
        style=GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
        descriptions=(_description(spec) for _, spec, _ in ordered),
    )
    root = ET.fromstring(kml)
    document = root.find(f"{_KML}Document")
    assert document is not None  # Produced by reference_paths_to_kml above.
    placemarks = list(document.findall(f"{_KML}Placemark"))
    if len(placemarks) != len(ordered):
        raise RuntimeError("KML exporter did not produce one Placemark per component")
    for placemark in placemarks:
        document.remove(placemark)

    airport_folders: dict[str, ET.Element] = {}
    runway_folders: dict[tuple[str, str], ET.Element] = {}
    side_folders: dict[tuple[str, str, str], ET.Element] = {}
    for placemark, (icao, spec, _) in zip(placemarks, ordered, strict=True):
        airport_folder = airport_folders.get(icao)
        if airport_folder is None:
            airport_folder = _folder(document, icao)
            airport_folders[icao] = airport_folder
        runway_key = (icao, spec.runway.designation)
        runway_folder = runway_folders.get(runway_key)
        if runway_folder is None:
            runway_folder = _folder(airport_folder, f"RWY{spec.runway.designation}")
            runway_folders[runway_key] = runway_folder
        side_key = (*runway_key, spec.side.value.upper())
        side_folder = side_folders.get(side_key)
        if side_folder is None:
            side_folder = _folder(runway_folder, spec.side.value.upper())
            side_folders[side_key] = side_folder
        side_folder.append(placemark)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _write_airport_exports(
    destination: Path,
    icao: str,
    pairs: tuple[tuple[TrafficPatternSpec, tuple[PolylineReferencePath, ...]], ...],
) -> tuple[Path, ...]:
    written: list[Path] = []
    for spec, components in pairs:
        description = _description(spec)
        written.append(
            write_kml(
                reference_paths_to_kml(
                    components,
                    name=pattern_identity(spec),
                    style=GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
                    descriptions=(description,) * len(components),
                ),
                destination / f"{pattern_identity(spec)}_TRAFFIC_PATTERN.kml",
            )
        )
    all_paths = tuple(path for _, components in pairs for path in components)
    all_descriptions = tuple(
        _description(spec) for spec, components in pairs for _ in components
    )
    written.append(
        write_kml(
            reference_paths_to_kml(
                all_paths,
                name=f"{icao}_ALL_TRAFFIC_PATTERNS",
                style=GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
                descriptions=all_descriptions,
            ),
            destination / f"{icao}_ALL_TRAFFIC_PATTERNS.kml",
        )
    )
    written.append(
        write_kmz(
            _foldered_kml(((icao, pairs),), name=f"{icao} Traffic Patterns"),
            destination / f"{icao}_TRAFFIC_PATTERNS.kmz",
        )
    )
    return tuple(written)


def write_kyushu_traffic_pattern_exports(
    destination: str | Path,
    icao: str | None = None,
    **switches: bool,
) -> tuple[Path, ...]:
    """Write raw KML plus airport and Kyushu-wide Google Earth KMZ artifacts.

    A selected airport yields four pattern KML files, one combined raw KML and
    its KMZ.  With no selection this repeats for all eight airports and adds
    ``KYUSHU_TRAFFIC_PATTERNS.kmz``.
    """

    destination_path = Path(destination)
    if icao is not None:
        airport = _normalise_icao(icao)
        return _write_airport_exports(
            destination_path,
            airport,
            build_kyushu_traffic_patterns(airport, **switches),
        )

    all_pairs = tuple(
        (airport, build_kyushu_traffic_patterns(airport, **switches))
        for airport in KYUSHU_AIRPORTS
    )
    written = [
        path
        for airport, pairs in all_pairs
        for path in _write_airport_exports(destination_path, airport, pairs)
    ]
    written.append(
        write_kmz(
            _foldered_kml(all_pairs, name="Kyushu Traffic Patterns"),
            destination_path / "KYUSHU_TRAFFIC_PATTERNS.kmz",
        )
    )
    return tuple(written)


def main() -> None:
    """Write the Jupyter workflow's raw KML and KMZ artifacts from the CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--airport", choices=KYUSHU_AIRPORTS)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/kyushu-traffic-patterns")
    )
    for flag, default in (
        ("make-circle-before-downwind", True),
        ("make-270-before-downwind", True),
        ("make-circle-middle-downwind", True),
        ("make-circle-before-base", False),
        ("make-270-before-base", True),
    ):
        parser.add_argument(
            f"--{flag}", action=argparse.BooleanOptionalAction, default=default
        )
    args = vars(parser.parse_args())
    airport = args.pop("airport")
    destination = args.pop("output_dir")
    for path in write_kyushu_traffic_pattern_exports(destination, airport, **args):
        print(path)


if __name__ == "__main__":
    main()
