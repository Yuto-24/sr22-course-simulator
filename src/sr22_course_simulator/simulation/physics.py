"""Analytical relationships used by the quasi-steady integrator."""

from __future__ import annotations

from dataclasses import dataclass
import math

from sr22_course_simulator.environment.wind import WindVector
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.units import wrap_radians_2pi

STANDARD_GRAVITY_MPS2 = 9.80665


def coordinated_turn_rate_rad_s(
    true_airspeed_mps: float,
    bank_rad: float,
    *,
    gravity_mps2: float = STANDARD_GRAVITY_MPS2,
) -> float:
    """Ideal coordinated-turn heading rate ``g tan(bank) / TAS``."""

    speed = float(true_airspeed_mps)
    bank = float(bank_rad)
    if not math.isfinite(speed) or speed <= 0.0:
        raise ValidationError("true_airspeed_mps must be finite and positive")
    if not math.isfinite(bank) or not -math.pi / 2 < bank < math.pi / 2:
        raise ValidationError("bank_rad must lie strictly between -pi/2 and pi/2")
    return float(gravity_mps2) * math.tan(bank) / speed


def coordinated_turn_radius_m(
    true_airspeed_mps: float,
    bank_rad: float,
    *,
    gravity_mps2: float = STANDARD_GRAVITY_MPS2,
) -> float:
    """Signed ideal coordinated-turn radius; zero bank returns infinity."""

    rate = coordinated_turn_rate_rad_s(true_airspeed_mps, bank_rad, gravity_mps2=gravity_mps2)
    return math.inf if rate == 0.0 else float(true_airspeed_mps) / rate


def coordinated_load_factor(bank_rad: float) -> float:
    bank = float(bank_rad)
    if not math.isfinite(bank) or not -math.pi / 2 < bank < math.pi / 2:
        raise ValidationError("bank_rad must lie strictly between -pi/2 and pi/2")
    return 1.0 / math.cos(bank)


@dataclass(frozen=True, slots=True)
class VelocityENU:
    east_mps: float
    north_mps: float
    up_mps: float

    @property
    def horizontal_speed_mps(self) -> float:
        return math.hypot(self.east_mps, self.north_mps)

    @property
    def track_true_rad_or_none(self) -> float | None:
        """Return track when horizontal velocity defines one, otherwise ``None``.

        Zero horizontal velocity is a valid velocity result, but it does not
        geometrically define a track.  State propagation can use this optional
        form to apply its explicit previous-track policy without manufacturing
        a direction of travel.
        """

        if self.horizontal_speed_mps == 0.0:
            return None
        return wrap_radians_2pi(math.atan2(self.east_mps, self.north_mps))

    @property
    def track_true_rad(self) -> float:
        """Return defined track, retaining the strict legacy accessor."""

        track = self.track_true_rad_or_none
        if track is None:
            raise ValidationError("track is undefined for zero horizontal velocity")
        return track


def air_velocity_enu(
    *,
    true_airspeed_mps: float,
    heading_true_rad: float,
    flight_path_angle_rad: float,
) -> VelocityENU:
    speed = float(true_airspeed_mps)
    gamma = float(flight_path_angle_rad)
    if not math.isfinite(speed) or speed <= 0.0:
        raise ValidationError("true_airspeed_mps must be finite and positive")
    if not math.isfinite(gamma) or not -math.pi / 2 < gamma < math.pi / 2:
        raise ValidationError("flight_path_angle_rad must lie strictly between -pi/2 and pi/2")
    horizontal = speed * math.cos(gamma)
    return VelocityENU(
        east_mps=horizontal * math.sin(heading_true_rad),
        north_mps=horizontal * math.cos(heading_true_rad),
        up_mps=speed * math.sin(gamma),
    )


def add_wind(air_velocity: VelocityENU, wind: WindVector) -> VelocityENU:
    return VelocityENU(
        east_mps=air_velocity.east_mps + wind.east_mps,
        north_mps=air_velocity.north_mps + wind.north_mps,
        up_mps=air_velocity.up_mps + wind.up_mps,
    )
