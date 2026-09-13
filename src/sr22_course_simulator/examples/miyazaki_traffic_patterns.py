"""Generate Miyazaki Airport Make-Circle traffic-pattern ReferencePaths."""

from __future__ import annotations

import argparse
from pathlib import Path

from sr22_course_simulator.aircraft import GeoPosition
from sr22_course_simulator.data.airports import RJFM
from sr22_course_simulator.data.airports.rjfm_short_downwind import (
    RJFM_SHORT_DOWNWIND_CIRCLE_SOURCE,
    RJFM_SHORT_DOWNWIND_CIRCLE_TANGENCY,
    RJFM_SHORT_DOWNWIND_COORDINATES,
    RJFM_SHORT_DOWNWIND_ENTRY_RWY27_COORDINATES,
    RJFM_SHORT_DOWNWIND_ENTRY_RWY27_SOURCE,
    RJFM_SHORT_DOWNWIND_SOURCE,
)
from sr22_course_simulator.export import (
    GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
    KmlPathStyle,
    reference_path_to_kml,
    reference_paths_to_kml,
    write_kml,
)
from sr22_course_simulator.path import (
    PatternLabel,
    PatternSide,
    PathPoint,
    PolylineReferencePath,
    ShortDownwindCircleSpec,
    TrafficPatternSpec,
    generate_short_downwind_circle,
    generate_traffic_pattern,
)
from sr22_course_simulator.path.traffic_pattern import (
    generate_traffic_pattern_components,
)
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation


RJFM_TRAFFIC_PATTERN_SOURCE = SourceCitation(
    document_title="宮崎空港及びその周辺における訓練飛行実施要領（R6.5.1改正）p.1; 学訓 第4章 改正19 p.1-2",
    extraction_method="task-provided primary-source transcription and task-selected simplification",
    transformations=(
        "pattern geometry resolved from RWY Center Point and true-bearing vectors",
        "110 KTAS and coordinated-turn physics used to derive turn radii",
        "linear 10 deg/s roll transitions integrated deterministically",
        "aviation-facing distances and altitudes converted to SI units",
        "runway surface at the aiming marker linearly interpolated between thresholds",
    ),
    notes=(
        "宮崎訓練飛行実施要領 p.1: 北側場周を通常使用し、状況により南側も使用可; 場周高度1000 ft（MSLとは明記しない）; 離陸後は滑走路末端通過後かつ700 ft以上で旋回開始",
        "学訓 第4章 p.2図: 場周高度は1000 ft AGLと図示される",
        "学訓 第4章 p.1-2: 通常はTPAの300 ft手前からCrosswind旋回; 上昇中20 deg、Level Off後とDownwind/Baseは30 deg、Finalは標準25 deg（最大30 deg）",
        "学訓 第4章 p.2図: Downwind 1.5 NMと宮崎の1.2 NM騒音軽減指定。RWY27の指定地点通過後旋回も現ReferencePathでは再現しない",
        "今回のReferencePathはtask指定に従い場周高度を1000 ft MSLとして適用し、ユーザー選択により1.2 NMを相反するCrosswind/Baseの共通axisとして扱い、Aiming MarkerからUpwind turn開始までに比例上昇し、Crosswindを30 degで生成する簡略化である",
        "110 KTAS, normal/final bank, 22 deg ordinary Base bank, 10 deg/s roll, and 3 deg final are task-provided",
        "Make Circle and Make 270 Before Downwind/Base are independent user-selected paths",
        "ReferencePath geometry contains no wind or time-indexed aircraft dynamics",
    ),
)

RJFM_COMBINED_PATTERN_FILENAME = "RJFM_ALL_MAKE_CIRCLE_PATTERNS.kml"
RJFM_SHORT_DOWNWIND_FILENAME = "RJFM_SHORT_DOWNWIND.kml"
RJFM_SHORT_DOWNWIND_CIRCLE_FILENAME = "RJFM_SHORT_DOWNWIND_CIRCLE.kml"
RJFM_SHORT_DOWNWIND_ENTRY_RWY27_FILENAME = "RJFM_SHORT_DOWNWIND_ENTRY_RWY27.kml"
RJFM_SHORT_DOWNWIND_COMBINED_FILENAME = "RJFM_SHORT_DOWNWIND_WITH_CIRCLE.kml"

RJFM_RWY09_TRAFFIC_PATTERN_STYLE = KmlPathStyle(
    extrude=True,
    line_color="ffffff00",  # opaque cyan in KML AABBGGRR order
    line_width=1.0,
    fill_color="1affffcc",  # approximately 10% opaque pale cyan
    fill=True,
    outline=False,
)
RJFM_RWY27_TRAFFIC_PATTERN_STYLE = KmlPathStyle(
    extrude=True,
    line_color="ff00aaff",  # opaque orange in KML AABBGGRR order
    line_width=1.0,
    fill_color="1a80d4ff",  # approximately 10% opaque pale orange
    fill=True,
    outline=False,
)


def _rjfm_runway_styles(
    *,
    rwy09_line_color: str,
    rwy09_fill_color: str,
    rwy27_line_color: str,
    rwy27_fill_color: str,
) -> dict[str, KmlPathStyle]:
    """Build fixed-opacity/width Google Earth styles keyed by runway."""

    return {
        "09": KmlPathStyle(
            extrude=True,
            line_color=rwy09_line_color,
            line_width=1.0,
            fill_color=rwy09_fill_color,
            fill=True,
            outline=False,
        ),
        "27": KmlPathStyle(
            extrude=True,
            line_color=rwy27_line_color,
            line_width=1.0,
            fill_color=rwy27_fill_color,
            fill=True,
            outline=False,
        ),
    }


def rjfm_traffic_pattern_specs(
    *,
    altitude_ft: float = 1_000.0,
    downwind_offset_nm: float = 1.5,
    crosswind_base_extension_nm: float = 1.2,
    true_airspeed_kt: float = 110.0,
    normal_bank_deg: float = 30.0,
    final_bank_deg: float = 25.0,
    roll_rate_deg_s: float = 10.0,
    glide_path_deg: float = 3.0,
    sample_interval_s: float = 0.25,
    make_circle_before_downwind: bool = True,
    make_circle_middle_downwind: bool = True,
    make_circle_before_base: bool = False,
    make_270_before_downwind: bool = True,
    make_270_before_base: bool = True,
    downwind_turn_bank_deg: float = 22.0,
    base_turn_bank_deg: float = 22.0,
) -> tuple[TrafficPatternSpec, ...]:
    """Build four RJFM Make-Circle traffic-pattern specifications."""

    runway_09 = RJFM.runway("09")
    runway_27 = RJFM.runway("27")
    common = {
        "airport": RJFM,
        "altitude_ft": altitude_ft,
        "downwind_offset_nm": downwind_offset_nm,
        "crosswind_base_extension_nm": crosswind_base_extension_nm,
        "true_airspeed_kt": true_airspeed_kt,
        "normal_bank_deg": normal_bank_deg,
        "final_bank_deg": final_bank_deg,
        "roll_rate_deg_s": roll_rate_deg_s,
        "glide_path_deg": glide_path_deg,
        "sample_interval_s": sample_interval_s,
        "make_circle_before_downwind": make_circle_before_downwind,
        "make_circle_middle_downwind": make_circle_middle_downwind,
        "make_circle_before_base": make_circle_before_base,
        "make_270_before_downwind": make_270_before_downwind,
        "make_270_before_base": make_270_before_base,
        "downwind_turn_bank_deg": downwind_turn_bank_deg,
        "base_turn_bank_deg": base_turn_bank_deg,
        "source": RJFM_TRAFFIC_PATTERN_SOURCE,
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
    """Derive one Make-Circle output name from its paired specification."""

    return (
        f"RJFM_RWY{spec.runway.designation}_"
        f"{spec.label.value.upper()}_MAKE_CIRCLES.kml"
    )


RJFM_PATTERN_FILENAMES = tuple(
    _rjfm_pattern_filename(spec) for spec in rjfm_traffic_pattern_specs()
)


def _build_rjfm_traffic_pattern_pairs(
    **parameters: float | bool,
) -> tuple[tuple[TrafficPatternSpec, PolylineReferencePath], ...]:
    specs = rjfm_traffic_pattern_specs(**parameters)
    return tuple((spec, generate_traffic_pattern(spec)) for spec in specs)


def _build_rjfm_traffic_pattern_component_pairs(
    **parameters: float | bool,
) -> tuple[
    tuple[TrafficPatternSpec, tuple[PolylineReferencePath, ...]],
    ...,
]:
    specs = rjfm_traffic_pattern_specs(**parameters)
    return tuple(
        (spec, generate_traffic_pattern_components(spec)) for spec in specs
    )


def build_rjfm_short_downwind() -> PolylineReferencePath:
    """Return the task-provided Short Downwind coordinates unchanged."""

    points = tuple(
        PathPoint(
            position=GeoPosition(latitude_deg, longitude_deg),
            altitude_m=altitude_m,
            label=(
                "short_downwind_start"
                if index == 0
                else "short_downwind_end"
                if index == len(RJFM_SHORT_DOWNWIND_COORDINATES) - 1
                else None
            ),
        )
        for index, (longitude_deg, latitude_deg, altitude_m) in enumerate(
            RJFM_SHORT_DOWNWIND_COORDINATES
        )
    )
    return PolylineReferencePath(
        name="RJFM Short Downwind",
        path_points=points,
        evidence=EvidenceKind.ASSUMED,
        citation=RJFM_SHORT_DOWNWIND_SOURCE,
    )


def build_rjfm_short_downwind_entry_rwy27() -> PolylineReferencePath:
    """Return the task-provided RWY27 Short Downwind entry unchanged."""

    points = tuple(
        PathPoint(
            position=GeoPosition(latitude_deg, longitude_deg),
            altitude_m=altitude_m,
            label=(
                "short_downwind_entry_rwy27_start"
                if index == 0
                else "short_downwind_entry_rwy27_end"
                if index == len(RJFM_SHORT_DOWNWIND_ENTRY_RWY27_COORDINATES) - 1
                else None
            ),
        )
        for index, (longitude_deg, latitude_deg, altitude_m) in enumerate(
            RJFM_SHORT_DOWNWIND_ENTRY_RWY27_COORDINATES
        )
    )
    return PolylineReferencePath(
        name="RJFM Short Downwind Entry RWY27",
        path_points=points,
        evidence=EvidenceKind.ASSUMED,
        citation=RJFM_SHORT_DOWNWIND_ENTRY_RWY27_SOURCE,
    )
def rjfm_short_downwind_circle_spec(
    *,
    true_airspeed_kt: float = 110.0,
    bank_deg: float = 22.0,
    point_count: int = 145,
) -> ShortDownwindCircleSpec:
    """Build the requested steady-circle specification for Short Downwind."""

    longitude_deg, latitude_deg, altitude_m = RJFM_SHORT_DOWNWIND_CIRCLE_TANGENCY
    return ShortDownwindCircleSpec(
        name="RJFM Circle on Short Downwind",
        runway=RJFM.runway("09"),
        tangency_position=GeoPosition(latitude_deg, longitude_deg),
        altitude_m=altitude_m,
        true_airspeed_kt=true_airspeed_kt,
        bank_deg=bank_deg,
        point_count=point_count,
        source=RJFM_SHORT_DOWNWIND_CIRCLE_SOURCE,
    )


def build_rjfm_short_downwind_paths(
    *,
    circle_true_airspeed_kt: float = 110.0,
    circle_bank_deg: float = 22.0,
    circle_point_count: int = 145,
) -> tuple[PolylineReferencePath, PolylineReferencePath, PolylineReferencePath]:
    """Return RWY27 entry, unchanged Short Downwind, and resized circle."""

    circle_spec = rjfm_short_downwind_circle_spec(
        true_airspeed_kt=circle_true_airspeed_kt,
        bank_deg=circle_bank_deg,
        point_count=circle_point_count,
    )
    return (
        build_rjfm_short_downwind_entry_rwy27(),
        build_rjfm_short_downwind(),
        generate_short_downwind_circle(circle_spec),
    )


def build_rjfm_traffic_patterns(
    *,
    altitude_ft: float = 1_000.0,
    downwind_offset_nm: float = 1.5,
    crosswind_base_extension_nm: float = 1.2,
    true_airspeed_kt: float = 110.0,
    normal_bank_deg: float = 30.0,
    final_bank_deg: float = 25.0,
    roll_rate_deg_s: float = 10.0,
    glide_path_deg: float = 3.0,
    sample_interval_s: float = 0.25,
    make_circle_before_downwind: bool = True,
    make_circle_middle_downwind: bool = True,
    make_circle_before_base: bool = False,
    make_270_before_downwind: bool = True,
    make_270_before_base: bool = True,
    downwind_turn_bank_deg: float = 22.0,
    base_turn_bank_deg: float = 22.0,
) -> tuple[PolylineReferencePath, ...]:
    """Generate all four RJFM Make-Circle traffic-pattern paths."""

    pairs = _build_rjfm_traffic_pattern_pairs(
        altitude_ft=altitude_ft,
        downwind_offset_nm=downwind_offset_nm,
        crosswind_base_extension_nm=crosswind_base_extension_nm,
        true_airspeed_kt=true_airspeed_kt,
        normal_bank_deg=normal_bank_deg,
        final_bank_deg=final_bank_deg,
        roll_rate_deg_s=roll_rate_deg_s,
        glide_path_deg=glide_path_deg,
        sample_interval_s=sample_interval_s,
        make_circle_before_downwind=make_circle_before_downwind,
        make_circle_middle_downwind=make_circle_middle_downwind,
        make_circle_before_base=make_circle_before_base,
        make_270_before_downwind=make_270_before_downwind,
        make_270_before_base=make_270_before_base,
        downwind_turn_bank_deg=downwind_turn_bank_deg,
        base_turn_bank_deg=base_turn_bank_deg,
    )
    return tuple(path for _, path in pairs)


def build_rjfm_traffic_pattern_components(
    *,
    altitude_ft: float = 1_000.0,
    downwind_offset_nm: float = 1.5,
    crosswind_base_extension_nm: float = 1.2,
    true_airspeed_kt: float = 110.0,
    normal_bank_deg: float = 30.0,
    final_bank_deg: float = 25.0,
    roll_rate_deg_s: float = 10.0,
    glide_path_deg: float = 3.0,
    sample_interval_s: float = 0.25,
    make_circle_before_downwind: bool = True,
    make_circle_middle_downwind: bool = True,
    make_circle_before_base: bool = False,
    make_270_before_downwind: bool = True,
    make_270_before_base: bool = True,
    downwind_turn_bank_deg: float = 22.0,
    base_turn_bank_deg: float = 22.0,
) -> tuple[PolylineReferencePath, ...]:
    """Generate flattened base/circle/270 components for all four patterns."""

    pairs = _build_rjfm_traffic_pattern_component_pairs(
        altitude_ft=altitude_ft,
        downwind_offset_nm=downwind_offset_nm,
        crosswind_base_extension_nm=crosswind_base_extension_nm,
        true_airspeed_kt=true_airspeed_kt,
        normal_bank_deg=normal_bank_deg,
        final_bank_deg=final_bank_deg,
        roll_rate_deg_s=roll_rate_deg_s,
        glide_path_deg=glide_path_deg,
        sample_interval_s=sample_interval_s,
        make_circle_before_downwind=make_circle_before_downwind,
        make_circle_middle_downwind=make_circle_middle_downwind,
        make_circle_before_base=make_circle_before_base,
        make_270_before_downwind=make_270_before_downwind,
        make_270_before_base=make_270_before_base,
        downwind_turn_bank_deg=downwind_turn_bank_deg,
        base_turn_bank_deg=base_turn_bank_deg,
    )
    return tuple(path for _, components in pairs for path in components)


def write_rjfm_traffic_pattern_kmls(
    destination: str | Path,
    *,
    altitude_ft: float = 1_000.0,
    downwind_offset_nm: float = 1.5,
    crosswind_base_extension_nm: float = 1.2,
    true_airspeed_kt: float = 110.0,
    normal_bank_deg: float = 30.0,
    final_bank_deg: float = 25.0,
    roll_rate_deg_s: float = 10.0,
    glide_path_deg: float = 3.0,
    sample_interval_s: float = 0.25,
    make_circle_before_downwind: bool = True,
    make_circle_middle_downwind: bool = True,
    make_circle_before_base: bool = False,
    make_270_before_downwind: bool = True,
    make_270_before_base: bool = True,
    downwind_turn_bank_deg: float = 22.0,
    base_turn_bank_deg: float = 22.0,
    rwy09_line_color: str = RJFM_RWY09_TRAFFIC_PATTERN_STYLE.line_color,
    rwy09_fill_color: str = RJFM_RWY09_TRAFFIC_PATTERN_STYLE.fill_color,
    rwy27_line_color: str = RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
    rwy27_fill_color: str = RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
    include_combined: bool = True,
) -> tuple[Path, ...]:
    """Write runway-colored individual and combined Google Earth KML files."""

    destination_path = Path(destination)
    component_pairs = _build_rjfm_traffic_pattern_component_pairs(
        altitude_ft=altitude_ft,
        downwind_offset_nm=downwind_offset_nm,
        crosswind_base_extension_nm=crosswind_base_extension_nm,
        true_airspeed_kt=true_airspeed_kt,
        normal_bank_deg=normal_bank_deg,
        final_bank_deg=final_bank_deg,
        roll_rate_deg_s=roll_rate_deg_s,
        glide_path_deg=glide_path_deg,
        sample_interval_s=sample_interval_s,
        make_circle_before_downwind=make_circle_before_downwind,
        make_circle_middle_downwind=make_circle_middle_downwind,
        make_circle_before_base=make_circle_before_base,
        make_270_before_downwind=make_270_before_downwind,
        make_270_before_base=make_270_before_base,
        downwind_turn_bank_deg=downwind_turn_bank_deg,
        base_turn_bank_deg=base_turn_bank_deg,
    )
    styles_by_runway = _rjfm_runway_styles(
        rwy09_line_color=rwy09_line_color,
        rwy09_fill_color=rwy09_fill_color,
        rwy27_line_color=rwy27_line_color,
        rwy27_fill_color=rwy27_fill_color,
    )
    written = [
        write_kml(
            reference_paths_to_kml(
                components,
                name=(
                    f"{spec.airport.icao} RWY{spec.runway.designation} "
                    f"{spec.label.value.upper()} Traffic Pattern Components"
                ),
                styles=(styles_by_runway[spec.runway.designation],) * len(components),
            ),
            destination_path / _rjfm_pattern_filename(spec),
        )
        for spec, components in component_pairs
    ]
    if include_combined:
        combined_paths = tuple(
            path
            for _, components in component_pairs
            for path in components
        )
        written.append(
            write_kml(
                reference_paths_to_kml(
                    combined_paths,
                    name="RJFM Traffic Patterns and Independent Turn Paths",
                    styles=tuple(
                        styles_by_runway[spec.runway.designation]
                        for spec, components in component_pairs
                        for _ in components
                    ),
                ),
                destination_path / RJFM_COMBINED_PATTERN_FILENAME,
            )
        )
    return tuple(written)


def write_rjfm_short_downwind_kmls(
    destination: str | Path,
    *,
    circle_true_airspeed_kt: float = 110.0,
    circle_bank_deg: float = 22.0,
    circle_point_count: int = 145,
    rwy27_line_color: str = RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
    rwy27_fill_color: str = RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
    include_combined: bool = True,
) -> tuple[Path, ...]:
    """Write Short Downwind and its physics-sized circle as Google Earth KML."""

    destination_path = Path(destination)
    entry_rwy27, short_downwind, circle = build_rjfm_short_downwind_paths(
        circle_true_airspeed_kt=circle_true_airspeed_kt,
        circle_bank_deg=circle_bank_deg,
        circle_point_count=circle_point_count,
    )
    rwy27_style = _rjfm_runway_styles(
        rwy09_line_color=RJFM_RWY09_TRAFFIC_PATTERN_STYLE.line_color,
        rwy09_fill_color=RJFM_RWY09_TRAFFIC_PATTERN_STYLE.fill_color,
        rwy27_line_color=rwy27_line_color,
        rwy27_fill_color=rwy27_fill_color,
    )["27"]
    written = [
        write_kml(
            reference_path_to_kml(
                entry_rwy27,
                style=rwy27_style,
            ),
            destination_path / RJFM_SHORT_DOWNWIND_ENTRY_RWY27_FILENAME,
        ),
        write_kml(
            reference_path_to_kml(
                short_downwind,
                style=GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE,
            ),
            destination_path / RJFM_SHORT_DOWNWIND_FILENAME,
        ),
        write_kml(
            reference_path_to_kml(
                circle,
                style=rwy27_style,
            ),
            destination_path / RJFM_SHORT_DOWNWIND_CIRCLE_FILENAME,
        ),
    ]
    if include_combined:
        written.append(
            write_kml(
                reference_paths_to_kml(
                    (entry_rwy27, short_downwind, circle),
                    name="RJFM Short Downwind Entry, Path, and Circle",
                    styles=(
                        rwy27_style,
                        rwy27_style,
                        rwy27_style,
                    ),
                ),
                destination_path / RJFM_SHORT_DOWNWIND_COMBINED_FILENAME,
            )
        )
    return tuple(written)


def main() -> None:
    """Write RJFM Make-Circle KML artifacts from command-line parameters."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/traffic-patterns"),
    )
    parser.add_argument("--altitude-ft", type=float, default=1_000.0)
    parser.add_argument("--downwind-offset-nm", type=float, default=1.5)
    parser.add_argument("--crosswind-base-extension-nm", type=float, default=1.2)
    parser.add_argument("--true-airspeed-kt", type=float, default=110.0)
    parser.add_argument("--normal-bank-deg", type=float, default=30.0)
    parser.add_argument("--final-bank-deg", type=float, default=25.0)
    parser.add_argument("--downwind-turn-bank-deg", type=float, default=22.0)
    parser.add_argument("--base-turn-bank-deg", type=float, default=22.0)
    parser.add_argument("--roll-rate-deg-s", type=float, default=10.0)
    parser.add_argument("--glide-path-deg", type=float, default=3.0)
    parser.add_argument("--sample-interval-s", type=float, default=0.25)
    parser.add_argument(
        "--short-downwind-circle-true-airspeed-kt",
        type=float,
        default=110.0,
    )
    parser.add_argument("--short-downwind-circle-bank-deg", type=float, default=22.0)
    parser.add_argument(
        "--rwy09-line-color",
        default=RJFM_RWY09_TRAFFIC_PATTERN_STYLE.line_color,
        help="RWY09 line color in KML AABBGGRR order",
    )
    parser.add_argument(
        "--rwy09-fill-color",
        default=RJFM_RWY09_TRAFFIC_PATTERN_STYLE.fill_color,
        help="RWY09 fill color in KML AABBGGRR order",
    )
    parser.add_argument(
        "--rwy27-line-color",
        default=RJFM_RWY27_TRAFFIC_PATTERN_STYLE.line_color,
        help="RWY27 line color in KML AABBGGRR order",
    )
    parser.add_argument(
        "--rwy27-fill-color",
        default=RJFM_RWY27_TRAFFIC_PATTERN_STYLE.fill_color,
        help="RWY27 fill color in KML AABBGGRR order",
    )
    parser.add_argument(
        "--make-circle-before-downwind",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--make-circle-middle-downwind",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--make-circle-before-base",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--make-270-before-downwind",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--make-270-before-base",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()
    written = list(write_rjfm_traffic_pattern_kmls(
        args.output_dir,
        altitude_ft=args.altitude_ft,
        downwind_offset_nm=args.downwind_offset_nm,
        crosswind_base_extension_nm=args.crosswind_base_extension_nm,
        true_airspeed_kt=args.true_airspeed_kt,
        normal_bank_deg=args.normal_bank_deg,
        final_bank_deg=args.final_bank_deg,
        downwind_turn_bank_deg=args.downwind_turn_bank_deg,
        base_turn_bank_deg=args.base_turn_bank_deg,
        roll_rate_deg_s=args.roll_rate_deg_s,
        glide_path_deg=args.glide_path_deg,
        sample_interval_s=args.sample_interval_s,
        make_circle_before_downwind=args.make_circle_before_downwind,
        make_circle_middle_downwind=args.make_circle_middle_downwind,
        make_circle_before_base=args.make_circle_before_base,
        make_270_before_downwind=args.make_270_before_downwind,
        make_270_before_base=args.make_270_before_base,
        rwy09_line_color=args.rwy09_line_color,
        rwy09_fill_color=args.rwy09_fill_color,
        rwy27_line_color=args.rwy27_line_color,
        rwy27_fill_color=args.rwy27_fill_color,
    ))
    written.extend(
        write_rjfm_short_downwind_kmls(
            args.output_dir,
            circle_true_airspeed_kt=args.short_downwind_circle_true_airspeed_kt,
            circle_bank_deg=args.short_downwind_circle_bank_deg,
            rwy27_line_color=args.rwy27_line_color,
            rwy27_fill_color=args.rwy27_fill_color,
        )
    )
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
