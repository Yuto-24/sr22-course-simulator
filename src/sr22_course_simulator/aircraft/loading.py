"""Mass-based loading and fuel bookkeeping.

Fuel is represented by mass.  A volume conversion is deliberately not supplied
because it requires a documented fuel-density convention.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from sr22_course_simulator.errors import ValidationError


def _nonnegative_finite(name: str, value: float) -> float:
    numeric = float(value)
    if isinstance(value, bool) or not math.isfinite(numeric) or numeric < 0.0:
        raise ValidationError(f"{name} must be a finite non-negative mass")
    return numeric


@dataclass(frozen=True, slots=True)
class MassItem:
    label: str
    mass_kg: float

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValidationError("MassItem label must not be empty")
        object.__setattr__(self, "mass_kg", _nonnegative_finite("mass_kg", self.mass_kg))


@dataclass(frozen=True, slots=True)
class Loading:
    """Non-fuel aircraft/loading masses sufficient to calculate gross mass."""

    empty_aircraft_mass_kg: float
    payload: tuple[MassItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "empty_aircraft_mass_kg",
            _nonnegative_finite("empty_aircraft_mass_kg", self.empty_aircraft_mass_kg),
        )
        object.__setattr__(self, "payload", tuple(self.payload))
        if any(not isinstance(item, MassItem) for item in self.payload):
            raise ValidationError("payload must contain only MassItem values")

    @property
    def non_fuel_mass_kg(self) -> float:
        return self.empty_aircraft_mass_kg + sum(item.mass_kg for item in self.payload)

    def gross_mass_kg(self, fuel_mass_kg: float) -> float:
        return self.non_fuel_mass_kg + _nonnegative_finite("fuel_mass_kg", fuel_mass_kg)


@dataclass(frozen=True, slots=True)
class FuelState:
    initial_mass_kg: float
    remaining_mass_kg: float

    def __post_init__(self) -> None:
        initial = _nonnegative_finite("initial_mass_kg", self.initial_mass_kg)
        remaining = _nonnegative_finite("remaining_mass_kg", self.remaining_mass_kg)
        if remaining > initial:
            raise ValidationError("remaining fuel cannot exceed initial fuel without refueling")
        object.__setattr__(self, "initial_mass_kg", initial)
        object.__setattr__(self, "remaining_mass_kg", remaining)

    @classmethod
    def initial(cls, mass_kg: float) -> "FuelState":
        return cls(initial_mass_kg=mass_kg, remaining_mass_kg=mass_kg)

    @property
    def burned_mass_kg(self) -> float:
        return self.initial_mass_kg - self.remaining_mass_kg

    def burn(self, *, fuel_flow_kg_s: float, dt_s: float) -> "FuelState":
        flow = _nonnegative_finite("fuel_flow_kg_s", fuel_flow_kg_s)
        duration = _nonnegative_finite("dt_s", dt_s)
        burned = min(self.remaining_mass_kg, flow * duration)
        return FuelState(self.initial_mass_kg, self.remaining_mass_kg - burned)
