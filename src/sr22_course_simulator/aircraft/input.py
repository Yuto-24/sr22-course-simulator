"""Pilot-relevant flight inputs for the current coordinated-flight model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.units import degrees_to_radians, radians_to_degrees


class FlapSetting(str, Enum):
    """Discrete flap selections exposed by the training-facing API."""

    RETRACTED = "retracted"
    HALF = "half"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class FlightInput:
    """A commanded Pitch/Bank/PWR/Flap combination.

    Heading, altitude, Gear and Rudder are intentionally absent.  Heading and
    altitude are states; the target aircraft has fixed landing gear; intentional
    sideslip is outside current scope.
    """

    pitch_rad: float
    bank_rad: float
    power_fraction: float
    flap: FlapSetting = FlapSetting.RETRACTED

    def __post_init__(self) -> None:
        values = (self.pitch_rad, self.bank_rad, self.power_fraction)
        if any(isinstance(value, bool) or not math.isfinite(value) for value in values):
            raise ValidationError("FlightInput values must be finite real numbers")
        if not -math.pi / 2 < self.pitch_rad < math.pi / 2:
            raise ValidationError("pitch_rad must lie strictly between -pi/2 and pi/2")
        if not -math.pi / 2 < self.bank_rad < math.pi / 2:
            raise ValidationError("bank_rad must lie strictly between -pi/2 and pi/2")
        if not 0.0 <= self.power_fraction <= 1.0:
            raise ValidationError("power_fraction must be in [0, 1]")
        if not isinstance(self.flap, FlapSetting):
            raise ValidationError("flap must be a FlapSetting")

    @classmethod
    def from_degrees(
        cls,
        *,
        pitch_deg: float,
        bank_deg: float,
        power_pct: float,
        flap: FlapSetting = FlapSetting.RETRACTED,
    ) -> "FlightInput":
        return cls(
            pitch_rad=degrees_to_radians(pitch_deg),
            bank_rad=degrees_to_radians(bank_deg),
            power_fraction=float(power_pct) / 100.0,
            flap=flap,
        )

    @property
    def pitch_deg(self) -> float:
        return radians_to_degrees(self.pitch_rad)

    @property
    def bank_deg(self) -> float:
        return radians_to_degrees(self.bank_rad)

    @property
    def power_pct(self) -> float:
        return self.power_fraction * 100.0
