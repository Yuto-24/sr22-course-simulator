"""Wind-independent curved airport traffic-pattern geometry."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import math

from sr22_course_simulator.airport import AirportSpec, RunwaySpec
from sr22_course_simulator.aircraft.state import GeoPosition
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.geometry import displace_position, enu_displacement
from sr22_course_simulator.path.reference import PathPoint, PolylineReferencePath
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation
from sr22_course_simulator.simulation.physics import (
    STANDARD_GRAVITY_MPS2,
    coordinated_turn_radius_m,
)
from sr22_course_simulator.units import (
    feet_to_metres,
    knots_to_metres_per_second,
    nautical_miles_to_metres,
)


LONG_RUNWAY_THRESHOLD_M = 2_400.0
LONG_RUNWAY_AIMING_MARKER_DISTANCE_M = 400.0
SHORT_RUNWAY_AIMING_MARKER_DISTANCE_M = 300.0


class PatternSide(StrEnum):
    """Pattern side relative to the landing runway direction."""

    LEFT = "left"
    RIGHT = "right"


class PatternLabel(StrEnum):
    """Geographic display label for a pattern."""

    NORTH = "north"
    SOUTH = "south"


@dataclass(frozen=True, slots=True)
class TurnProfileSample:
    """One deterministic sample of an ideal coordinated turn."""

    elapsed_s: float
    distance_m: float
    x_m: float
    y_m: float
    heading_change_rad: float
    bank_rad: float


@dataclass(frozen=True, slots=True)
class CoordinatedTurnProfile:
    """Sampled roll-in, steady-bank, and roll-out turn geometry."""

    signed_sweep_rad: float
    nominal_radius_m: float
    roll_duration_s: float
    steady_duration_s: float
    samples: tuple[TurnProfileSample, ...]
    evidence: EvidenceKind


def _finite(value: float, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} must be finite")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be finite") from exc
    if not math.isfinite(numeric):
        raise ValidationError(f"{field_name} must be finite")
    return numeric


@dataclass(frozen=True, slots=True)
class TrafficPatternSpec:
    """Task-defined parameters for a wind-independent traffic ReferencePath."""

    airport: AirportSpec
    runway: RunwaySpec
    side: PatternSide
    label: PatternLabel
    altitude_ft: float
    downwind_offset_nm: float
    crosswind_base_extension_nm: float
    source: SourceCitation
    true_airspeed_kt: float = 110.0
    normal_bank_deg: float = 30.0
    final_bank_deg: float = 25.0
    roll_rate_deg_s: float = 10.0
    glide_path_deg: float = 3.0
    sample_interval_s: float = 0.25
    make_circle_before_downwind: bool = True
    make_circle_middle_downwind: bool = True
    make_circle_before_base: bool = False
    make_270_before_downwind: bool = True
    make_270_before_base: bool = True
    downwind_turn_bank_deg: float = 22.0
    base_turn_bank_deg: float = 22.0

    def __post_init__(self) -> None:
        if not isinstance(self.airport, AirportSpec):
            raise ValidationError("traffic-pattern airport must be an AirportSpec")
        if not isinstance(self.runway, RunwaySpec):
            raise ValidationError("traffic-pattern runway must be a RunwaySpec")
        if self.runway not in self.airport.runways:
            raise ValidationError("traffic-pattern runway must belong to its airport")
        if not isinstance(self.side, PatternSide):
            raise ValidationError("traffic-pattern side must be PatternSide")
        if not isinstance(self.label, PatternLabel):
            raise ValidationError("traffic-pattern label must be PatternLabel")
        if not isinstance(self.source, SourceCitation):
            raise ValidationError("traffic-pattern source must be a SourceCitation")
        for field_name in (
            "make_circle_before_downwind",
            "make_circle_middle_downwind",
            "make_circle_before_base",
            "make_270_before_downwind",
            "make_270_before_base",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValidationError(f"{field_name} must be bool")
        non_negative = (
            "altitude_ft",
            "downwind_offset_nm",
            "crosswind_base_extension_nm",
        )
        positive = (
            "true_airspeed_kt",
            "normal_bank_deg",
            "final_bank_deg",
            "downwind_turn_bank_deg",
            "base_turn_bank_deg",
            "roll_rate_deg_s",
            "glide_path_deg",
            "sample_interval_s",
        )
        for field_name in non_negative + positive:
            numeric = _finite(getattr(self, field_name), field_name)
            if field_name in non_negative and numeric < 0.0:
                raise ValidationError(f"{field_name} must be non-negative")
            if field_name in positive and numeric <= 0.0:
                raise ValidationError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, numeric)
        for field_name in (
            "normal_bank_deg",
            "final_bank_deg",
            "downwind_turn_bank_deg",
            "base_turn_bank_deg",
            "glide_path_deg",
        ):
            if getattr(self, field_name) >= 90.0:
                raise ValidationError(f"{field_name} must be below 90 degrees")

    @property
    def name(self) -> str:
        """Return a stable human-readable path name."""

        return (
            f"{self.airport.icao} RWY{self.runway.designation} "
            f"{self.label.value.upper()} Traffic Pattern with Make Circles"
        )

    @property
    def normal_turn_radius_m(self) -> float:
        """Return the physics-derived steady normal-turn radius."""

        return abs(
            coordinated_turn_radius_m(
                knots_to_metres_per_second(self.true_airspeed_kt),
                math.radians(self.normal_bank_deg),
            )
        )

    @property
    def final_turn_radius_m(self) -> float:
        """Return the physics-derived steady final-turn radius."""

        return abs(
            coordinated_turn_radius_m(
                knots_to_metres_per_second(self.true_airspeed_kt),
                math.radians(self.final_bank_deg),
            )
        )

    @property
    def base_turn_radius_m(self) -> float:
        """Return the physics-derived ordinary Base-turn radius."""

        return abs(
            coordinated_turn_radius_m(
                knots_to_metres_per_second(self.true_airspeed_kt),
                math.radians(self.base_turn_bank_deg),
            )
        )

    @property
    def downwind_turn_radius_m(self) -> float:
        """Return the physics-derived ordinary Downwind-turn radius."""

        return abs(
            coordinated_turn_radius_m(
                knots_to_metres_per_second(self.true_airspeed_kt),
                math.radians(self.downwind_turn_bank_deg),
            )
        )


def aiming_marker_distance_m(runway: RunwaySpec) -> float:
    """Return the task-defined aiming-marker distance from landing threshold."""

    return (
        LONG_RUNWAY_AIMING_MARKER_DISTANCE_M
        if runway.declared_length_m >= LONG_RUNWAY_THRESHOLD_M
        else SHORT_RUNWAY_AIMING_MARKER_DISTANCE_M
    )


def aiming_marker_elevation_ft(runway: RunwaySpec) -> float:
    """Linearly interpolate runway-surface elevation at the aiming marker."""

    fraction = aiming_marker_distance_m(runway) / runway.measured_length_m
    return runway.threshold_elevation_a_ft + fraction * (
        runway.threshold_elevation_b_ft - runway.threshold_elevation_a_ft
    )


def generate_coordinated_turn_profile(
    *,
    true_airspeed_mps: float,
    nominal_bank_deg: float,
    roll_rate_deg_s: float,
    signed_sweep_deg: float,
    sample_interval_s: float,
    marker_sweeps_deg: tuple[float, ...] = (),
) -> CoordinatedTurnProfile:
    """Generate constant-speed turn geometry including linear roll transitions."""

    speed = _finite(true_airspeed_mps, "true_airspeed_mps")
    bank_deg = _finite(nominal_bank_deg, "nominal_bank_deg")
    roll_rate_deg = _finite(roll_rate_deg_s, "roll_rate_deg_s")
    signed_sweep_deg = _finite(signed_sweep_deg, "signed_sweep_deg")
    interval = _finite(sample_interval_s, "sample_interval_s")
    if speed <= 0.0 or not 0.0 < bank_deg < 90.0:
        raise ValidationError("turn speed and nominal bank must be positive and supported")
    if roll_rate_deg <= 0.0 or interval <= 0.0 or signed_sweep_deg == 0.0:
        raise ValidationError("turn roll rate, sample interval, and sweep must be non-zero")

    direction = 1.0 if signed_sweep_deg > 0.0 else -1.0
    sweep = abs(math.radians(signed_sweep_deg))
    bank = math.radians(bank_deg)
    roll_rate = math.radians(roll_rate_deg)
    roll_duration = bank / roll_rate
    ramp_angle = (
        STANDARD_GRAVITY_MPS2
        / (speed * roll_rate)
        * -math.log(math.cos(bank))
    )
    if 2.0 * ramp_angle >= sweep:
        raise ValidationError("turn sweep is too small for the requested bank and roll rate")
    nominal_rate = STANDARD_GRAVITY_MPS2 * math.tan(bank) / speed
    steady_duration = (sweep - 2.0 * ramp_angle) / nominal_rate
    total_duration = 2.0 * roll_duration + steady_duration

    def bank_magnitude_at(time_s: float) -> float:
        if time_s <= roll_duration:
            return roll_rate * time_s
        if time_s <= roll_duration + steady_duration:
            return bank
        return max(0.0, bank - roll_rate * (time_s - roll_duration - steady_duration))

    def turn_magnitude_at(time_s: float) -> float:
        if time_s <= roll_duration:
            current_bank = roll_rate * time_s
            return (
                STANDARD_GRAVITY_MPS2
                / (speed * roll_rate)
                * -math.log(math.cos(current_bank))
            )
        if time_s <= roll_duration + steady_duration:
            return ramp_angle + nominal_rate * (time_s - roll_duration)
        remaining_bank = max(
            0.0,
            bank - roll_rate * (time_s - roll_duration - steady_duration),
        )
        roll_out_angle = (
            STANDARD_GRAVITY_MPS2
            / (speed * roll_rate)
            * math.log(math.cos(remaining_bank) / math.cos(bank))
        )
        return ramp_angle + nominal_rate * steady_duration + roll_out_angle

    times = {0.0, roll_duration, roll_duration + steady_duration, total_duration}
    count = int(math.floor(total_duration / interval))
    regular_times = tuple(index * interval for index in range(1, count + 1))
    times.update(regular_times)
    # Reflect samples around the midpoint so a full 360-degree roll profile
    # returns to its straight-leg axis without numerical lateral drift.
    times.update(total_duration - time_s for time_s in regular_times)
    for marker_deg in marker_sweeps_deg:
        marker = math.radians(_finite(marker_deg, "marker_sweep_deg"))
        if not ramp_angle <= marker <= sweep - ramp_angle:
            raise ValidationError("turn marker must lie in the steady-bank phase")
        times.add(roll_duration + (marker - ramp_angle) / nominal_rate)

    x_m = 0.0
    y_m = 0.0
    previous_time = 0.0
    previous_turn = 0.0
    samples = [TurnProfileSample(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]
    for time_s in sorted(times - {0.0}):
        duration = time_s - previous_time
        current_turn = turn_magnitude_at(time_s)
        signed_delta = direction * (current_turn - previous_turn)
        heading = direction * previous_turn
        if abs(signed_delta) < 1e-15:
            x_m += speed * duration * math.cos(heading)
            y_m += speed * duration * math.sin(heading)
        else:
            effective_rate = signed_delta / duration
            next_heading = heading + signed_delta
            x_m += speed / effective_rate * (
                math.sin(next_heading) - math.sin(heading)
            )
            y_m += speed / effective_rate * (
                -math.cos(next_heading) + math.cos(heading)
            )
        samples.append(
            TurnProfileSample(
                elapsed_s=time_s,
                distance_m=speed * time_s,
                x_m=x_m,
                y_m=y_m,
                heading_change_rad=direction * current_turn,
                bank_rad=direction * bank_magnitude_at(time_s),
            )
        )
        previous_time = time_s
        previous_turn = current_turn

    samples[-1] = TurnProfileSample(
        elapsed_s=total_duration,
        distance_m=speed * total_duration,
        x_m=samples[-1].x_m,
        y_m=samples[-1].y_m,
        heading_change_rad=direction * sweep,
        bank_rad=0.0,
    )
    return CoordinatedTurnProfile(
        signed_sweep_rad=direction * sweep,
        nominal_radius_m=abs(coordinated_turn_radius_m(speed, direction * bank)),
        roll_duration_s=roll_duration,
        steady_duration_s=steady_duration,
        samples=tuple(samples),
        evidence=EvidenceKind.PHYSICS_DERIVED,
    )


@dataclass(frozen=True, slots=True)
class _LocalPoint:
    x_m: float
    y_m: float
    label: str | None = None


def _cross(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _unit(heading_rad: float) -> tuple[float, float]:
    return math.cos(heading_rad), math.sin(heading_rad)


def _profile_displacements(
    profile: CoordinatedTurnProfile,
    start_heading_rad: float,
) -> tuple[tuple[float, float], ...]:
    cosine = math.cos(start_heading_rad)
    sine = math.sin(start_heading_rad)
    return tuple(
        (
            cosine * sample.x_m - sine * sample.y_m,
            sine * sample.x_m + cosine * sample.y_m,
        )
        for sample in profile.samples
    )


def _fit_turn_to_corner(
    *,
    corner: tuple[float, float],
    start_heading_rad: float,
    profile: CoordinatedTurnProfile,
    start_label: str,
    end_label: str,
    milestone_label: str | None = None,
) -> tuple[_LocalPoint, ...]:
    displacements = _profile_displacements(profile, start_heading_rad)
    end_heading = start_heading_rad + profile.signed_sweep_rad
    incoming = _unit(start_heading_rad)
    outgoing = _unit(end_heading)
    denominator = _cross(incoming, outgoing)
    if abs(denominator) < 1e-10:
        raise ValidationError("corner turn must finish on a non-parallel leg")
    offset = -_cross(displacements[-1], outgoing) / denominator
    start_x = corner[0] + offset * incoming[0]
    start_y = corner[1] + offset * incoming[1]

    milestone_index: int | None = None
    if milestone_label is not None:
        milestone_index = min(
            range(len(profile.samples)),
            key=lambda index: abs(
                abs(profile.samples[index].heading_change_rad) - math.tau
            ),
        )
    points = []
    for index, (dx_m, dy_m) in enumerate(displacements):
        label = None
        if index == 0:
            label = start_label
        elif index == len(displacements) - 1:
            label = end_label
        elif index == milestone_index:
            label = milestone_label
        points.append(_LocalPoint(start_x + dx_m, start_y + dy_m, label))
    return tuple(points)


def _fit_full_circle_to_leg_midpoint(
    *,
    midpoint: tuple[float, float],
    start_heading_rad: float,
    profile: CoordinatedTurnProfile,
    start_label: str,
    end_label: str,
) -> tuple[_LocalPoint, ...]:
    displacements = _profile_displacements(profile, start_heading_rad)
    leg = _unit(start_heading_rad)
    normal = (-leg[1], leg[0])
    if abs(displacements[-1][0] * normal[0] + displacements[-1][1] * normal[1]) > 0.05:
        raise ValidationError("full-circle roll profile does not return to its leg")
    start_x = midpoint[0] - 0.5 * displacements[-1][0]
    start_y = midpoint[1] - 0.5 * displacements[-1][1]
    return tuple(
        _LocalPoint(
            start_x + dx_m,
            start_y + dy_m,
            start_label if index == 0 else end_label if index == len(displacements) - 1 else None,
        )
        for index, (dx_m, dy_m) in enumerate(displacements)
    )


def _append_segment(points: list[_LocalPoint], segment: tuple[_LocalPoint, ...]) -> None:
    if not segment:
        return
    if points and math.hypot(
        points[-1].x_m - segment[0].x_m,
        points[-1].y_m - segment[0].y_m,
    ) < 1e-8:
        points.extend(segment[1:])
    else:
        points.extend(segment)


def _append_straight(points: list[_LocalPoint], target: _LocalPoint) -> None:
    if not points or math.hypot(points[-1].x_m - target.x_m, points[-1].y_m - target.y_m) > 1e-8:
        points.append(target)


def _position_from_runway_center(
    runway: RunwaySpec,
    *,
    along_m: float,
    lateral_m: float,
    side: PatternSide,
) -> GeoPosition:
    """Resolve runway-axis coordinates from the computed RWY Center Point."""

    runway_east, runway_north = runway.runway_unit_vector
    if side is PatternSide.LEFT:
        normal_east, normal_north = runway.left_normal_unit_vector
    else:
        normal_east, normal_north = runway.right_normal_unit_vector
    return displace_position(
        runway.center_point,
        east_m=runway_east * along_m + normal_east * lateral_m,
        north_m=runway_north * along_m + normal_north * lateral_m,
    )


def generate_traffic_pattern(spec: TrafficPatternSpec) -> PolylineReferencePath:
    """Generate a curved Make-Circle traffic ``ReferencePath``.

    The path uses ideal coordinated-turn geometry only to construct a desired,
    wind-independent ground path. It remains a ``ReferencePath`` rather than a
    time-indexed aircraft ``Trajectory``.
    """

    runway = spec.runway
    half_runway_m = runway.measured_length_m / 2.0
    downwind_offset_m = nautical_miles_to_metres(spec.downwind_offset_nm)
    crosswind_base_extension_m = nautical_miles_to_metres(
        spec.crosswind_base_extension_nm
    )
    pattern_altitude_m = feet_to_metres(spec.altitude_ft)
    speed_mps = knots_to_metres_per_second(spec.true_airspeed_kt)

    landing_station_m = -half_runway_m
    # The normal-pattern skeleton fixes both stations 1.2 NM beyond their
    # respective thresholds.  The crosswind leg for one direction is therefore
    # the reciprocal direction's base line in the same physical location.
    departure_station_m = half_runway_m + crosswind_base_extension_m
    base_station_m = landing_station_m - crosswind_base_extension_m
    aiming_station_m = landing_station_m + aiming_marker_distance_m(runway)

    normal_90 = generate_coordinated_turn_profile(
        true_airspeed_mps=speed_mps,
        nominal_bank_deg=spec.normal_bank_deg,
        roll_rate_deg_s=spec.roll_rate_deg_s,
        signed_sweep_deg=90.0,
        sample_interval_s=spec.sample_interval_s,
    )
    before_downwind_profile: CoordinatedTurnProfile | None = None
    ordinary_downwind_profile: CoordinatedTurnProfile | None = None
    if spec.make_270_before_downwind:
        before_downwind_profile = generate_coordinated_turn_profile(
            true_airspeed_mps=speed_mps,
            nominal_bank_deg=spec.normal_bank_deg,
            roll_rate_deg_s=spec.roll_rate_deg_s,
            signed_sweep_deg=-630.0 if spec.make_circle_before_downwind else -270.0,
            sample_interval_s=spec.sample_interval_s,
            marker_sweeps_deg=(360.0,) if spec.make_circle_before_downwind else (),
        )
    else:
        ordinary_downwind_profile = generate_coordinated_turn_profile(
            true_airspeed_mps=speed_mps,
            nominal_bank_deg=spec.downwind_turn_bank_deg,
            roll_rate_deg_s=spec.roll_rate_deg_s,
            signed_sweep_deg=90.0,
            sample_interval_s=spec.sample_interval_s,
        )
    before_base_profile: CoordinatedTurnProfile | None = None
    if spec.make_270_before_base:
        before_base_profile = generate_coordinated_turn_profile(
            true_airspeed_mps=speed_mps,
            nominal_bank_deg=spec.normal_bank_deg,
            roll_rate_deg_s=spec.roll_rate_deg_s,
            signed_sweep_deg=-630.0 if spec.make_circle_before_base else -270.0,
            sample_interval_s=spec.sample_interval_s,
            marker_sweeps_deg=(360.0,) if spec.make_circle_before_base else (),
        )
    ordinary_base_profile: CoordinatedTurnProfile | None = None
    if not spec.make_270_before_base:
        ordinary_base_profile = generate_coordinated_turn_profile(
            true_airspeed_mps=speed_mps,
            nominal_bank_deg=spec.base_turn_bank_deg,
            roll_rate_deg_s=spec.roll_rate_deg_s,
            signed_sweep_deg=90.0,
            sample_interval_s=spec.sample_interval_s,
        )
    final_90 = generate_coordinated_turn_profile(
        true_airspeed_mps=speed_mps,
        nominal_bank_deg=spec.final_bank_deg,
        roll_rate_deg_s=spec.roll_rate_deg_s,
        signed_sweep_deg=90.0,
        sample_interval_s=spec.sample_interval_s,
    )

    departure_turn = _fit_turn_to_corner(
        corner=(departure_station_m, 0.0),
        start_heading_rad=0.0,
        profile=normal_90,
        start_label="departure_turn_start",
        end_label="departure_turn_end",
    )
    before_downwind_turn: tuple[_LocalPoint, ...] = ()
    ordinary_downwind_turn: tuple[_LocalPoint, ...] = ()
    if before_downwind_profile is not None:
        before_downwind_turn = _fit_turn_to_corner(
            corner=(departure_station_m, downwind_offset_m),
            start_heading_rad=math.pi / 2.0,
            profile=before_downwind_profile,
            start_label="before_downwind_turn_start",
            end_label="before_downwind_turn_end",
            milestone_label=(
                "before_downwind_circle_complete"
                if spec.make_circle_before_downwind
                else None
            ),
        )
    else:
        if ordinary_downwind_profile is None:
            raise AssertionError("ordinary Downwind-turn profile was not generated")
        ordinary_downwind_turn = _fit_turn_to_corner(
            corner=(departure_station_m, downwind_offset_m),
            start_heading_rad=math.pi / 2.0,
            profile=ordinary_downwind_profile,
            start_label="downwind_turn_start",
            end_label="downwind_turn_end",
        )
    downwind_entry_turn = before_downwind_turn or ordinary_downwind_turn
    before_base_turn: tuple[_LocalPoint, ...] = ()
    ordinary_base_turn: tuple[_LocalPoint, ...] = ()
    if before_base_profile is not None:
        before_base_turn = _fit_turn_to_corner(
            corner=(base_station_m, downwind_offset_m),
            start_heading_rad=math.pi,
            profile=before_base_profile,
            start_label="before_base_turn_start",
            end_label="before_base_turn_end",
            milestone_label=(
                "before_base_circle_complete" if spec.make_circle_before_base else None
            ),
        )
    else:
        if ordinary_base_profile is None:
            raise AssertionError("ordinary Base-turn profile was not generated")
        ordinary_base_turn = _fit_turn_to_corner(
            corner=(base_station_m, downwind_offset_m),
            start_heading_rad=math.pi,
            profile=ordinary_base_profile,
            start_label="base_turn_start",
            end_label="base_turn_end",
        )
    final_turn = _fit_turn_to_corner(
        corner=(base_station_m, 0.0),
        start_heading_rad=3.0 * math.pi / 2.0,
        profile=final_90,
        start_label="final_turn_start",
        end_label="final_turn_end",
    )

    middle_downwind_turn: tuple[_LocalPoint, ...] = ()
    if spec.make_circle_middle_downwind:
        middle_downwind_profile = generate_coordinated_turn_profile(
            true_airspeed_mps=speed_mps,
            nominal_bank_deg=spec.normal_bank_deg,
            roll_rate_deg_s=spec.roll_rate_deg_s,
            signed_sweep_deg=-360.0,
            sample_interval_s=spec.sample_interval_s,
        )
        downwind_destination = (
            before_base_turn[0]
            if before_base_turn
            else ordinary_base_turn[0]
        )
        downwind_midpoint = (
            0.5 * (downwind_entry_turn[-1].x_m + downwind_destination.x_m),
            downwind_offset_m,
        )
        middle_downwind_turn = _fit_full_circle_to_leg_midpoint(
            midpoint=downwind_midpoint,
            start_heading_rad=math.pi,
            profile=middle_downwind_profile,
            start_label="middle_downwind_turn_start",
            end_label="middle_downwind_circle_complete",
        )

    # The complete circuit begins at the runway-length-dependent aiming marker,
    # follows Takeoff/Upwind, and finishes at that same marker on Final.
    local_points: list[_LocalPoint] = [
        _LocalPoint(aiming_station_m, 0.0, "takeoff_aiming_marker")
    ]
    _append_segment(local_points, departure_turn)
    _append_straight(local_points, downwind_entry_turn[0])
    _append_segment(local_points, downwind_entry_turn)
    if middle_downwind_turn:
        _append_straight(local_points, middle_downwind_turn[0])
        _append_segment(local_points, middle_downwind_turn)
    if before_base_turn:
        _append_straight(local_points, before_base_turn[0])
        _append_segment(local_points, before_base_turn)
    else:
        _append_straight(local_points, ordinary_base_turn[0])
        _append_segment(local_points, ordinary_base_turn)
    _append_straight(local_points, final_turn[0])
    _append_segment(local_points, final_turn)
    _append_straight(
        local_points,
        _LocalPoint(landing_station_m, 0.0, "landing_threshold"),
    )
    _append_straight(local_points, _LocalPoint(aiming_station_m, 0.0, "aiming_marker"))

    labels = {point.label: index for index, point in enumerate(local_points) if point.label}
    upwind_turn_start = labels["departure_turn_start"]
    descent_start = labels[
        "before_base_turn_start" if spec.make_270_before_base else "base_turn_start"
    ]
    final_rollout = labels["final_turn_end"]
    cumulative = [0.0]
    for previous, current in zip(local_points, local_points[1:]):
        cumulative.append(
            cumulative[-1] + math.hypot(current.x_m - previous.x_m, current.y_m - previous.y_m)
        )

    aiming_elevation_m = feet_to_metres(aiming_marker_elevation_ft(runway))
    glide_slope = math.tan(math.radians(spec.glide_path_deg))
    final_rollout_altitude_m = aiming_elevation_m + (
        aiming_station_m - local_points[final_rollout].x_m
    ) * glide_slope
    if final_rollout_altitude_m >= pattern_altitude_m:
        raise ValidationError("pattern altitude must be above the computed final rollout altitude")
    descent_distance = cumulative[final_rollout] - cumulative[descent_start]

    climb_distance = cumulative[upwind_turn_start]
    if climb_distance <= 0.0:
        raise ValidationError("upwind climb segment must have positive length")

    path_points = []
    for index, point in enumerate(local_points):
        if index <= upwind_turn_start:
            # Completing this proportional climb before Crosswind is a
            # task-selected simplification, not an aircraft-performance model.
            altitude_m = aiming_elevation_m + cumulative[index] / climb_distance * (
                pattern_altitude_m - aiming_elevation_m
            )
        elif index <= descent_start:
            altitude_m = pattern_altitude_m
        elif index <= final_rollout:
            fraction = (cumulative[index] - cumulative[descent_start]) / descent_distance
            altitude_m = pattern_altitude_m + fraction * (
                final_rollout_altitude_m - pattern_altitude_m
            )
        else:
            altitude_m = aiming_elevation_m + (
                aiming_station_m - point.x_m
            ) * glide_slope
        path_points.append(
            PathPoint(
                position=_position_from_runway_center(
                    runway,
                    along_m=point.x_m,
                    lateral_m=point.y_m,
                    side=spec.side,
                ),
                altitude_m=altitude_m,
                label=point.label,
            )
        )

    return PolylineReferencePath(
        name=spec.name,
        path_points=tuple(path_points),
        evidence=EvidenceKind.ASSUMPTION_DEPENDENT,
        citation=spec.source,
    )


def _component_name(spec: TrafficPatternSpec, component: str) -> str:
    return (
        f"{spec.airport.icao} RWY{spec.runway.designation} "
        f"{spec.label.value.upper()} {component}"
    )


def _renamed_path(
    path: PolylineReferencePath,
    *,
    name: str,
) -> PolylineReferencePath:
    return PolylineReferencePath(
        name=name,
        path_points=path.points(),
        evidence=path.evidence,
        citation=path.citation,
    )


def _extract_path_component(
    path: PolylineReferencePath,
    *,
    start_label: str,
    end_label: str,
    name: str,
) -> PolylineReferencePath:
    points = path.points()
    indices = {
        point.label: index
        for index, point in enumerate(points)
        if point.label is not None
    }
    try:
        start_index = indices[start_label]
        end_index = indices[end_label]
    except KeyError as exc:
        raise AssertionError(f"missing traffic-pattern component label: {exc}") from exc
    return PolylineReferencePath(
        name=name,
        path_points=points[start_index : end_index + 1],
        evidence=path.evidence,
        citation=path.citation,
    )


def _local_coordinates_from_path_point(
    spec: TrafficPatternSpec,
    point: PathPoint,
) -> tuple[float, float]:
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


def _fit_profile_ending_at(
    *,
    end: tuple[float, float],
    start_heading_rad: float,
    profile: CoordinatedTurnProfile,
    start_label: str,
    end_label: str,
) -> tuple[_LocalPoint, ...]:
    displacements = _profile_displacements(profile, start_heading_rad)
    start_x = end[0] - displacements[-1][0]
    start_y = end[1] - displacements[-1][1]
    return tuple(
        _LocalPoint(
            start_x + dx_m,
            start_y + dy_m,
            start_label
            if index == 0
            else end_label
            if index == len(displacements) - 1
            else None,
        )
        for index, (dx_m, dy_m) in enumerate(displacements)
    )


def _constant_altitude_component(
    spec: TrafficPatternSpec,
    *,
    name: str,
    local_points: tuple[_LocalPoint, ...],
) -> PolylineReferencePath:
    altitude_m = feet_to_metres(spec.altitude_ft)
    return PolylineReferencePath(
        name=name,
        path_points=tuple(
            PathPoint(
                position=_position_from_runway_center(
                    spec.runway,
                    along_m=point.x_m,
                    lateral_m=point.y_m,
                    side=spec.side,
                ),
                altitude_m=altitude_m,
                label=point.label,
            )
            for point in local_points
        ),
        evidence=EvidenceKind.ASSUMPTION_DEPENDENT,
        citation=spec.source,
    )


def _profile_starting_at(
    *,
    start: tuple[float, float],
    start_heading_rad: float,
    profile: CoordinatedTurnProfile,
    start_label: str,
    end_label: str,
) -> tuple[_LocalPoint, ...]:
    """Place a turn profile at a fixed start point and incoming heading."""

    return tuple(
        _LocalPoint(
            start[0] + dx_m,
            start[1] + dy_m,
            start_label
            if index == 0
            else end_label
            if index == len(profile.samples) - 1
            else None,
        )
        for index, (dx_m, dy_m) in enumerate(
            _profile_displacements(profile, start_heading_rad)
        )
    )


def _horizontal_polyline_length(points: tuple[_LocalPoint, ...]) -> float:
    """Return the horizontal along-path length of local ReferencePath points."""

    return sum(
        math.hypot(current.x_m - previous.x_m, current.y_m - previous.y_m)
        for previous, current in zip(points, points[1:])
    )


def _insert_point_at_along_distance(
    points: tuple[_LocalPoint, ...],
    *,
    distance_m: float,
    label: str,
) -> tuple[_LocalPoint, ...]:
    """Insert a labeled point at an exact horizontal distance from path start."""

    total_distance_m = _horizontal_polyline_length(points)
    if not 0.0 <= distance_m < total_distance_m:
        raise ValidationError("insert distance must lie on the component before its merge")
    if math.isclose(distance_m, 0.0, abs_tol=1e-9):
        return (
            points[0],
            _LocalPoint(points[0].x_m, points[0].y_m, label),
            *points[1:],
        )
    accumulated_m = 0.0
    inserted: list[_LocalPoint] = [points[0]]
    for previous, current in zip(points, points[1:]):
        segment_m = math.hypot(current.x_m - previous.x_m, current.y_m - previous.y_m)
        next_accumulated_m = accumulated_m + segment_m
        if accumulated_m < distance_m < next_accumulated_m:
            fraction = (distance_m - accumulated_m) / segment_m
            inserted.append(
                _LocalPoint(
                    previous.x_m + fraction * (current.x_m - previous.x_m),
                    previous.y_m + fraction * (current.y_m - previous.y_m),
                    label,
                )
            )
        elif math.isclose(distance_m, next_accumulated_m, abs_tol=1e-9):
            inserted.append(_LocalPoint(current.x_m, current.y_m, label))
            accumulated_m = next_accumulated_m
            continue
        inserted.append(current)
        accumulated_m = next_accumulated_m
    return tuple(inserted)


def _component_with_altitudes(
    spec: TrafficPatternSpec,
    *,
    name: str,
    local_points: tuple[_LocalPoint, ...],
    descent_distance_m: float | None = None,
    merge_altitude_m: float | None = None,
) -> PolylineReferencePath:
    """Build a component, optionally descending over its final horizontal length."""

    pattern_altitude_m = feet_to_metres(spec.altitude_ft)
    if descent_distance_m is None:
        return _constant_altitude_component(spec, name=name, local_points=local_points)
    if merge_altitude_m is None:
        raise AssertionError("descending component requires a merge altitude")

    total_distance_m = _horizontal_polyline_length(local_points)
    if total_distance_m < descent_distance_m:
        raise ValidationError(
            "270 alternative path is shorter than the ordinary Base-turn length"
        )
    descent_start_distance_m = total_distance_m - descent_distance_m
    points = _insert_point_at_along_distance(
        local_points,
        distance_m=descent_start_distance_m,
        label="before_base_descent_start",
    )
    accumulated_m = 0.0
    path_points: list[PathPoint] = []
    for previous, current in zip(points, points[1:]):
        if not path_points:
            path_points.append(
                PathPoint(
                    position=_position_from_runway_center(
                        spec.runway,
                        along_m=previous.x_m,
                        lateral_m=previous.y_m,
                        side=spec.side,
                    ),
                    altitude_m=pattern_altitude_m,
                    label=previous.label,
                )
            )
        accumulated_m += math.hypot(current.x_m - previous.x_m, current.y_m - previous.y_m)
        descent_progress_m = max(0.0, accumulated_m - descent_start_distance_m)
        fraction = min(1.0, descent_progress_m / descent_distance_m)
        path_points.append(
            PathPoint(
                position=_position_from_runway_center(
                    spec.runway,
                    along_m=current.x_m,
                    lateral_m=current.y_m,
                    side=spec.side,
                ),
                altitude_m=pattern_altitude_m + fraction * (
                    merge_altitude_m - pattern_altitude_m
                ),
                label=current.label,
            )
        )
    return PolylineReferencePath(
        name=name,
        path_points=tuple(path_points),
        evidence=EvidenceKind.ASSUMPTION_DEPENDENT,
        citation=spec.source,
    )


def _outside_270_component_local_points(
    *,
    branch: _LocalPoint,
    merge: _LocalPoint,
    corner: tuple[float, float],
    start_heading_rad: float,
    profile: CoordinatedTurnProfile,
    branch_label: str,
    turn_start_label: str,
    turn_end_label: str,
    merge_label: str,
) -> tuple[_LocalPoint, ...]:
    """Connect a 270-degree turn tangentially between normal-path endpoints."""

    turn = _fit_turn_to_corner(
        corner=corner,
        start_heading_rad=start_heading_rad,
        profile=profile,
        start_label=turn_start_label,
        end_label=turn_end_label,
    )
    component = [_LocalPoint(branch.x_m, branch.y_m, branch_label)]
    _append_straight(component, turn[0])
    _append_segment(component, turn)
    _append_straight(component, _LocalPoint(merge.x_m, merge.y_m, merge_label))
    return tuple(component)


def generate_traffic_pattern_components(
    spec: TrafficPatternSpec,
) -> tuple[PolylineReferencePath, ...]:
    """Generate a clean base circuit and independently selectable turn paths.

    The first path always contains the ordinary 90-degree Downwind and Base
    turns, with no Make Circle or outside 270 embedded in it. Requested
    360-degree circles and 270-degree alternatives follow as standalone paths
    so KML clients can toggle each Placemark independently.
    """

    base_spec = replace(
        spec,
        make_circle_before_downwind=False,
        make_circle_middle_downwind=False,
        make_circle_before_base=False,
        make_270_before_downwind=False,
        make_270_before_base=False,
    )
    base_route = generate_traffic_pattern(base_spec)
    base = _renamed_path(
        base_route,
        name=_component_name(spec, "Traffic Pattern (No Circle / No 270)"),
    )
    base_labels = {
        point.label: point
        for point in base.points()
        if point.label is not None
    }
    base_label_indices = {
        point.label: index
        for index, point in enumerate(base.points())
        if point.label is not None
    }
    components: list[PolylineReferencePath] = [base]

    speed_mps = knots_to_metres_per_second(spec.true_airspeed_kt)
    outside_270_profile = generate_coordinated_turn_profile(
        true_airspeed_mps=speed_mps,
        nominal_bank_deg=spec.downwind_turn_bank_deg,
        roll_rate_deg_s=spec.roll_rate_deg_s,
        signed_sweep_deg=-270.0,
        sample_interval_s=spec.sample_interval_s,
    )
    half_runway_m = spec.runway.measured_length_m / 2.0
    crosswind_base_extension_m = nautical_miles_to_metres(
        spec.crosswind_base_extension_nm
    )
    departure_station_m = half_runway_m + crosswind_base_extension_m
    base_station_m = -half_runway_m - crosswind_base_extension_m
    downwind_offset_m = nautical_miles_to_metres(spec.downwind_offset_nm)
    downwind_270 = _fit_turn_to_corner(
        corner=(departure_station_m, downwind_offset_m),
        start_heading_rad=math.pi / 2.0,
        profile=outside_270_profile,
        start_label="before_downwind_turn_start",
        end_label="before_downwind_turn_end",
    )
    base_270 = _fit_turn_to_corner(
        corner=(base_station_m, downwind_offset_m),
        start_heading_rad=math.pi,
        profile=outside_270_profile,
        start_label="before_base_turn_start",
        end_label="before_base_turn_end",
    )

    circle_profile: CoordinatedTurnProfile | None = None
    if (
        spec.make_circle_before_downwind
        or spec.make_circle_middle_downwind
        or spec.make_circle_before_base
    ):
        circle_profile = generate_coordinated_turn_profile(
            true_airspeed_mps=speed_mps,
            nominal_bank_deg=spec.downwind_turn_bank_deg,
            roll_rate_deg_s=spec.roll_rate_deg_s,
            signed_sweep_deg=-360.0,
            sample_interval_s=spec.sample_interval_s,
        )

    if spec.make_circle_before_downwind:
        if circle_profile is None:
            raise AssertionError("circle profile was not generated")
        local_circle = _profile_starting_at(
            start=(downwind_270[0].x_m, downwind_270[0].y_m),
            start_heading_rad=math.pi / 2.0,
            profile=circle_profile,
            start_label="before_downwind_circle_start",
            end_label="before_downwind_circle_end",
        )
        components.append(
            _constant_altitude_component(
                spec,
                name=_component_name(spec, "Before Downwind Circle"),
                local_points=local_circle,
            )
        )

    if spec.make_270_before_downwind:
        components.append(
            _component_with_altitudes(
                spec,
                name=_component_name(spec, "Before Downwind 270"),
                local_points=_outside_270_component_local_points(
                    branch=_LocalPoint(
                        *_local_coordinates_from_path_point(
                            spec, base_labels["downwind_turn_start"]
                        )
                    ),
                    merge=_LocalPoint(
                        *_local_coordinates_from_path_point(
                            spec, base_labels["downwind_turn_end"]
                        )
                    ),
                    corner=(departure_station_m, downwind_offset_m),
                    start_heading_rad=math.pi / 2.0,
                    profile=outside_270_profile,
                    branch_label="before_downwind_branch",
                    turn_start_label="before_downwind_turn_start",
                    turn_end_label="before_downwind_turn_end",
                    merge_label="before_downwind_merge",
                ),
            )
        )

    if spec.make_circle_middle_downwind:
        if circle_profile is None:
            raise AssertionError("circle profile was not generated")
        downwind_start = _local_coordinates_from_path_point(
            spec,
            base_labels["downwind_turn_end"],
        )
        downwind_end = _local_coordinates_from_path_point(
            spec,
            base_labels["base_turn_start"],
        )
        local_circle = _fit_full_circle_to_leg_midpoint(
            midpoint=(
                0.5 * (downwind_start[0] + downwind_end[0]),
                0.5 * (downwind_start[1] + downwind_end[1]),
            ),
            start_heading_rad=math.pi,
            profile=circle_profile,
            start_label="middle_downwind_circle_start",
            end_label="middle_downwind_circle_end",
        )
        components.append(
            _constant_altitude_component(
                spec,
                name=_component_name(spec, "Middle Downwind Circle"),
                local_points=local_circle,
            )
        )

    if spec.make_circle_before_base:
        if circle_profile is None:
            raise AssertionError("circle profile was not generated")
        local_circle = _profile_starting_at(
            start=(base_270[0].x_m, base_270[0].y_m),
            start_heading_rad=math.pi,
            profile=circle_profile,
            start_label="before_base_circle_start",
            end_label="before_base_circle_end",
        )
        components.append(
            _constant_altitude_component(
                spec,
                name=_component_name(spec, "Before Base Circle"),
                local_points=local_circle,
            )
        )

    if spec.make_270_before_base:
        normal_base_turn = tuple(
            _LocalPoint(*_local_coordinates_from_path_point(spec, point))
            for point in base.points()[
                base_label_indices["base_turn_start"] : base_label_indices["base_turn_end"]
                + 1
            ]
        )
        components.append(
            _component_with_altitudes(
                spec,
                name=_component_name(spec, "Before Base 270"),
                local_points=_outside_270_component_local_points(
                    branch=_LocalPoint(
                        *_local_coordinates_from_path_point(
                            spec, base_labels["base_turn_start"]
                        )
                    ),
                    merge=_LocalPoint(
                        *_local_coordinates_from_path_point(
                            spec, base_labels["base_turn_end"]
                        )
                    ),
                    corner=(base_station_m, downwind_offset_m),
                    start_heading_rad=math.pi,
                    profile=outside_270_profile,
                    branch_label="before_base_branch",
                    turn_start_label="before_base_turn_start",
                    turn_end_label="before_base_turn_end",
                    merge_label="before_base_merge",
                ),
                descent_distance_m=_horizontal_polyline_length(normal_base_turn),
                merge_altitude_m=base_labels["base_turn_end"].altitude_m,
            )
        )

    return tuple(components)
