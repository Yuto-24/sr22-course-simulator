"""Generate four traffic patterns per Issue #9 airport with independent turns."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

from sr22_course_simulator.data.airports.traffic_profiles import (
    RJF_AIRPORTS,
    rjf_traffic_pattern_specs,
)
from sr22_course_simulator.export import (
    GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
    reference_paths_to_kml,
    write_kml,
)
from sr22_course_simulator.path import PolylineReferencePath, TrafficPatternSpec
from sr22_course_simulator.path.traffic_pattern import (
    generate_traffic_pattern_components,
)


def pattern_identity(spec: TrafficPatternSpec) -> str:
    """Return the canonical airport/runway/traffic-side output key."""
    return f"{spec.airport.icao}_RWY{spec.runway.designation}_{spec.side.value.upper()}"


def build_rjf_traffic_patterns(
    icao: str,
    **switches: bool,
) -> tuple[tuple[TrafficPatternSpec, tuple[PolylineReferencePath, ...]], ...]:
    """Return all four specs paired with normal path and selected components.

    Accepted switches are the five named Boolean arguments of
    ``rjf_traffic_pattern_specs``. The normal component is always first.
    """
    pairs = []
    for spec in rjf_traffic_pattern_specs(icao, **switches):
        prefix = f"{spec.airport.icao} RWY{spec.runway.designation} {spec.side.value.upper()} "
        components = tuple(
            replace(
                path, name=f"{pattern_identity(spec)} {path.name.removeprefix(prefix)}"
            )
            for path in generate_traffic_pattern_components(spec)
        )
        pairs.append((spec, components))
    return tuple(pairs)


def _description(spec: TrafficPatternSpec) -> str:
    return json.dumps(
        {
            "identity": pattern_identity(spec),
            "preferred": spec.preferred,
            "altitude_ft_msl": spec.altitude_ft,
            "descent_start": spec.descent_start.value,
            "notes": spec.notes,
            "operational_source": asdict(spec.source),
            "airport_source": asdict(spec.airport.source),
            "runway_source": asdict(spec.runway.source),
        },
        ensure_ascii=False,
        indent=2,
    )


def write_rjf_traffic_pattern_kmls(
    destination: str | Path,
    icao: str,
    **switches: bool,
) -> tuple[Path, ...]:
    """Write four individual KMLs and one combined KML, retaining provenance."""
    pairs = build_rjf_traffic_patterns(icao, **switches)
    destination = Path(destination)
    written = []
    all_paths = []
    all_descriptions = []
    for spec, components in pairs:
        descriptions = (_description(spec),) * len(components)
        written.append(
            write_kml(
                reference_paths_to_kml(
                    components,
                    name=pattern_identity(spec),
                    style=GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
                    descriptions=descriptions,
                ),
                destination / f"{pattern_identity(spec)}_TRAFFIC_PATTERN.kml",
            )
        )
        all_paths.extend(components)
        all_descriptions.extend(descriptions)
    airport = pairs[0][0].airport.icao
    written.append(
        write_kml(
            reference_paths_to_kml(
                all_paths,
                name=f"{airport}_ALL_TRAFFIC_PATTERNS",
                style=GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
                descriptions=all_descriptions,
            ),
            destination / f"{airport}_ALL_TRAFFIC_PATTERNS.kml",
        )
    )
    return tuple(written)


def main() -> None:
    """Generate one selected airport or all seven (35 KMLs by default)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--airport", choices=RJF_AIRPORTS, help="default: all seven airports"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/rjf-traffic-patterns")
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
    for icao in (airport,) if airport else RJF_AIRPORTS:
        for path in write_rjf_traffic_pattern_kmls(destination, icao, **args):
            print(path)


if __name__ == "__main__":
    main()
