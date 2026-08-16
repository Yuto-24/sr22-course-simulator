"""Mass-based loading and fuel bookkeeping.

Fuel is represented by mass.  A volume conversion is deliberately not supplied
because it requires a documented fuel-density convention.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from sr22_course_simulator.errors import ValidationError


def _nonnegative_finite(name: str, value: float) -> float:
    """
    Validate and normalize a mass value.
    
    Parameters:
    	name (str): Name used in the validation error message.
    	value (float): Mass value to validate.
    
    Returns:
    	float: The validated mass as a floating-point number.
    
    Raises:
    	ValidationError: If the value is boolean, non-finite, or negative.
    """
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
        """Return the aircraft mass excluding fuel."""
        return self.empty_aircraft_mass_kg + sum(item.mass_kg for item in self.payload)

    def gross_mass_kg(self, fuel_mass_kg: float) -> float:
        """
        Calculate the aircraft's gross mass including the specified fuel mass.
        
        Parameters:
        	fuel_mass_kg (float): Fuel mass in kilograms.
        
        Returns:
        	float: Total mass of the aircraft, payload, and fuel in kilograms.
        """
        return self.non_fuel_mass_kg + _nonnegative_finite("fuel_mass_kg", fuel_mass_kg)


@dataclass(frozen=True, slots=True)
class FuelState:
    initial_mass_kg: float
    remaining_mass_kg: float

    def __post_init__(self) -> None:
        """Validate and normalize the initial and remaining fuel masses.
        
        Raises:
            ValidationError: If either mass is invalid or remaining fuel exceeds initial fuel.
        """
        initial = _nonnegative_finite("initial_mass_kg", self.initial_mass_kg)
        remaining = _nonnegative_finite("remaining_mass_kg", self.remaining_mass_kg)
        if remaining > initial:
            raise ValidationError("remaining fuel cannot exceed initial fuel without refueling")
        object.__setattr__(self, "initial_mass_kg", initial)
        object.__setattr__(self, "remaining_mass_kg", remaining)

    @classmethod
    def initial(cls, mass_kg: float) -> "FuelState":
        """Create a fuel state with the specified mass initially fully remaining.
        
        Parameters:
        	mass_kg (float): Initial fuel mass in kilograms.
        
        Returns:
        	FuelState: A fuel state whose initial and remaining fuel masses are equal.
        """
        return cls(initial_mass_kg=mass_kg, remaining_mass_kg=mass_kg)

    @property
    def burned_mass_kg(self) -> float:
        """Calculate the amount of fuel burned.
        
        Returns:
            float: The initial fuel mass minus the remaining fuel mass.
        """
        return self.initial_mass_kg - self.remaining_mass_kg

    def burn(self, *, fuel_flow_kg_s: float, dt_s: float) -> "FuelState":
        """
        Calculate the fuel state after fuel consumption over a duration.
        
        Parameters:
        	fuel_flow_kg_s (float): Fuel consumption rate in kilograms per second.
        	dt_s (float): Elapsed time in seconds.
        
        Returns:
        	FuelState: The updated fuel state with remaining fuel reduced by the calculated burn amount.
        """
        flow = _nonnegative_finite("fuel_flow_kg_s", fuel_flow_kg_s)
        duration = _nonnegative_finite("dt_s", dt_s)
        burned = min(self.remaining_mass_kg, flow * duration)
        return FuelState(self.initial_mass_kg, self.remaining_mass_kg - burned)
