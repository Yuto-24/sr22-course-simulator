"""Generate Miyazaki Airport normal traffic-pattern reference paths."""

from __future__ import annotations

import argparse
from pathlib import Path

from sr22_course_simulator.data.airports import RJFM
from sr22_course_simulator.export import (
    reference_path_to_kml,
    reference_paths_to_kml,
    write_kml,
)
from sr22_course_simulator.path import (
    PatternLabel,
    PatternSide,
    PolylineReferencePath,
    TrafficPatternSpec,
    generate_traffic_pattern,
)
from sr22_course_simulator.provenance import SourceCitation


RJFM_NORMAL_PATTERN_SOURCE = SourceCitation(
    document_title="Aviation College operating material: RJFM normal traffic patterns",
    extraction_method="task-provided transcription",
    transformations=(
        "pattern geometry resolved from RWY Center Point and true-bearing vectors",
        "aviation-facing distances converted from NM to SI metres",
        "pattern altitude converted from ft MSL to SI metres",
    ),
    notes=(
        "crosswind extension 0.0 NM is an explicit task assumption",
        "ReferencePath geometry contains no wind or aircraft dynamics",
    ),
)

RJFM_COMBINED_PATTERN_FILENAME = "RJFM_ALL_NORMAL_PATTERNS.kml"


def rjfm_normal_pattern_specs(
    *,
    altitude_ft: float = 1_000.0,
    downwind_offset_nm: float = 1.5,
    base_extension_nm: float = 1.2,
    crosswind_extension_nm: float = 0.0,
) -> tuple[TrafficPatternSpec, ...]:
    """Build the four data-driven RJFM normal traffic-pattern specifications."""

    runway_09 = RJFM.runway("09")
    runway_27 = RJFM.runway("27")
    common = {
        "airport": RJFM,
        "altitude_ft": altitude_ft,
        "downwind_offset_nm": downwind_offset_nm,
        "base_extension_nm": base_extension_nm,
        "crosswind_extension_nm": crosswind_extension_nm,
        "source": RJFM_NORMAL_PATTERN_SOURCE,
    }
    return (
        TrafficPatternSpec(
            runway=runway_09,
            side=PatternSide.LEFT,
            label=PatternLabel.NORTH,
            **common,
        ),
        TrafficPatternSpec(
            runway=runway_09,
            side=PatternSide.RIGHT,
            label=PatternLabel.SOUTH,
            **common,
        ),
        TrafficPatternSpec(
            runway=runway_27,
            side=PatternSide.RIGHT,
            label=PatternLabel.NORTH,
            **common,
        ),
        TrafficPatternSpec(
            runway=runway_27,
            side=PatternSide.LEFT,
            label=PatternLabel.SOUTH,
            **common,
        ),
    )


def _rjfm_pattern_filename(spec: TrafficPatternSpec) -> str:
    """Derive one output name from the specification paired with its path."""

    return f"RJFM_RWY{spec.runway.designation}_{spec.label.value.upper()}.kml"


RJFM_PATTERN_FILENAMES = tuple(
    _rjfm_pattern_filename(spec) for spec in rjfm_normal_pattern_specs()
)


def _build_rjfm_normal_pattern_pairs(
    *,
    altitude_ft: float,
    downwind_offset_nm: float,
    base_extension_nm: float,
    crosswind_extension_nm: float,
) -> tuple[tuple[TrafficPatternSpec, PolylineReferencePath], ...]:
    specs = rjfm_normal_pattern_specs(
        altitude_ft=altitude_ft,
        downwind_offset_nm=downwind_offset_nm,
        base_extension_nm=base_extension_nm,
        crosswind_extension_nm=crosswind_extension_nm,
    )
    return tuple((spec, generate_traffic_pattern(spec)) for spec in specs)


def build_rjfm_normal_patterns(
    *,
    altitude_ft: float = 1_000.0,
    downwind_offset_nm: float = 1.5,
    base_extension_nm: float = 1.2,
    crosswind_extension_nm: float = 0.0,
) -> tuple[PolylineReferencePath, ...]:
    """Generate all four RJFM normal traffic-pattern reference paths."""

    pairs = _build_rjfm_normal_pattern_pairs(
        altitude_ft=altitude_ft,
        downwind_offset_nm=downwind_offset_nm,
        base_extension_nm=base_extension_nm,
        crosswind_extension_nm=crosswind_extension_nm,
    )
    return tuple(path for _, path in pairs)


def write_rjfm_normal_pattern_kmls(
    destination: str | Path,
    *,
    altitude_ft: float = 1_000.0,
    downwind_offset_nm: float = 1.5,
    base_extension_nm: float = 1.2,
    crosswind_extension_nm: float = 0.0,
    include_combined: bool = True,
) -> tuple[Path, ...]:
    """Write four individual KML files and optionally one combined KML file."""

    destination_path = Path(destination)
    pairs = _build_rjfm_normal_pattern_pairs(
        altitude_ft=altitude_ft,
        downwind_offset_nm=downwind_offset_nm,
        base_extension_nm=base_extension_nm,
        crosswind_extension_nm=crosswind_extension_nm,
    )
    paths = tuple(path for _, path in pairs)
    written = [
        write_kml(
            reference_path_to_kml(path),
            destination_path / _rjfm_pattern_filename(spec),
        )
        for spec, path in pairs
    ]
    if include_combined:
        written.append(
            write_kml(
                reference_paths_to_kml(
                    paths,
                    name="RJFM All Normal Traffic Patterns",
                ),
                destination_path / RJFM_COMBINED_PATTERN_FILENAME,
            )
        )
    return tuple(written)


def main() -> None:
    """Write RJFM traffic-pattern KML artifacts from command-line parameters."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/traffic-patterns"),
    )
    parser.add_argument("--altitude-ft", type=float, default=1_000.0)
    parser.add_argument("--downwind-offset-nm", type=float, default=1.5)
    parser.add_argument("--base-extension-nm", type=float, default=1.2)
    parser.add_argument("--crosswind-extension-nm", type=float, default=0.0)
    args = parser.parse_args()
    for path in write_rjfm_normal_pattern_kmls(
        args.output_dir,
        altitude_ft=args.altitude_ft,
        downwind_offset_nm=args.downwind_offset_nm,
        base_extension_nm=args.base_extension_nm,
        crosswind_extension_nm=args.crosswind_extension_nm,
    ):
        print(path)


if __name__ == "__main__":
    main()
