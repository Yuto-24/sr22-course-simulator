"""Goal and safety termination conditions with crossing interpolation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Protocol, runtime_checkable

from sr22_course_simulator.aircraft.state import AircraftState, InitialState
from sr22_course_simulator.environment import Environment
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.units import signed_angle_difference_rad


class TerminationRole(str, Enum):
    GOAL = "goal"
    PHASE_EXIT = "phase_exit"
    SAFETY = "safety"


@dataclass(frozen=True, slots=True)
class TerminationEvent:
    condition: str
    role: TerminationRole
    fraction_of_step: float
    message: str

    def __post_init__(self) -> None:
        """Validate that the event's step fraction is between 0 and 1."""
        if not 0.0 <= self.fraction_of_step <= 1.0:
            raise ValidationError("termination event fraction must be in [0, 1]")


@runtime_checkable
class TerminationCondition(Protocol):
    def evaluate(
        self,
        initial: InitialState,
        previous: AircraftState,
        current: AircraftState,
        environment: Environment,
    ) -> TerminationEvent | None:
        """
        Determine whether the termination condition has been reached during the step.
        
        Returns:
            TerminationEvent | None: The termination event when the condition is reached or crossed; otherwise, `None`.
        """


def _crossing_fraction(previous: float, current: float, target: float) -> float:
    """
    Calculate the clamped fraction of a step at which a value reaches a target.
    
    Parameters:
    	previous (float): The value at the start of the step.
    	current (float): The value at the end of the step.
    	target (float): The threshold value.
    
    Returns:
    	float: The target-crossing fraction between 0.0 and 1.0, or 0.0 when the values are unchanged.
    """
    if current == previous:
        return 0.0
    return max(0.0, min(1.0, (target - previous) / (current - previous)))


@dataclass(frozen=True, slots=True)
class ElapsedTime:
    duration_s: float
    role: TerminationRole = TerminationRole.GOAL

    def __post_init__(self) -> None:
        """Validate that the configured duration is finite and non-negative.
        
        Raises:
            ValidationError: If the duration is not finite or is negative.
        """
        if not math.isfinite(float(self.duration_s)) or self.duration_s < 0.0:
            raise ValidationError("duration_s must be finite and non-negative")

    def evaluate(self, initial, previous, current, environment) -> TerminationEvent | None:
        """
        Determines whether the configured elapsed-time limit is reached during the step.
        
        Returns:
            TerminationEvent | None: The elapsed-time event with its interpolated step
            position, or `None` if the limit is not reached.
        """
        target = initial.time_s + self.duration_s
        if previous.time_s <= target <= current.time_s:
            return TerminationEvent(
                "elapsed_time",
                self.role,
                _crossing_fraction(previous.time_s, current.time_s, target),
                f"Elapsed time reached {self.duration_s:g} s",
            )
        return None


@dataclass(frozen=True, slots=True)
class AltitudeAtOrBelow:
    altitude_m: float
    role: TerminationRole = TerminationRole.GOAL

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.altitude_m)):
            raise ValidationError("altitude_m must be finite")

    def evaluate(self, initial, previous, current, environment) -> TerminationEvent | None:
        """
        Determine whether the aircraft has reached or crossed the MSL altitude threshold.
        
        Returns:
            TerminationEvent | None: An event at the threshold crossing, or `None` if the
                threshold has not been reached.
        """
        if previous.altitude_m <= self.altitude_m:
            return TerminationEvent("altitude_at_or_below", self.role, 0.0, "Altitude threshold already met")
        if current.altitude_m <= self.altitude_m < previous.altitude_m:
            return TerminationEvent(
                "altitude_at_or_below",
                self.role,
                _crossing_fraction(previous.altitude_m, current.altitude_m, self.altitude_m),
                f"Altitude descended to {self.altitude_m:g} m MSL",
            )
        return None


@dataclass(frozen=True, slots=True)
class AltitudeAglAtOrBelow:
    height_agl_m: float
    role: TerminationRole = TerminationRole.SAFETY

    def __post_init__(self) -> None:
        """Validate that the AGL height limit is finite and non-negative.
        
        Raises:
            ValidationError: If `height_agl_m` is not finite or is less than zero.
        """
        if not math.isfinite(float(self.height_agl_m)) or self.height_agl_m < 0.0:
            raise ValidationError("height_agl_m must be finite and non-negative")

    def evaluate(self, initial, previous, current, environment) -> TerminationEvent | None:
        """
        Detects when the aircraft reaches the configured minimum height above ground level.
        
        Returns:
            TerminationEvent | None: The termination event at the start or interpolated
            crossing point of the step, or None if the minimum height was not reached.
        """
        previous_ground = environment.terrain.elevation_msl_m(previous.position)
        current_ground = environment.terrain.elevation_msl_m(current.position)
        previous_agl = previous.altitude_m - previous_ground
        current_agl = current.altitude_m - current_ground
        if previous_agl <= self.height_agl_m:
            return TerminationEvent("minimum_agl", self.role, 0.0, "Minimum AGL already reached")
        if current_agl <= self.height_agl_m < previous_agl:
            return TerminationEvent(
                "minimum_agl",
                self.role,
                _crossing_fraction(previous_agl, current_agl, self.height_agl_m),
                f"Minimum height {self.height_agl_m:g} m AGL reached",
            )
        return None


@dataclass(frozen=True, slots=True)
class AccumulatedTurn:
    turn_rad: float
    role: TerminationRole = TerminationRole.GOAL

    def __post_init__(self) -> None:
        """
        Validate that the accumulated turn target is finite and non-zero.
        
        Raises:
            ValidationError: If `turn_rad` is non-finite or equal to zero.
        """
        if not math.isfinite(float(self.turn_rad)) or self.turn_rad == 0.0:
            raise ValidationError("turn_rad must be finite and non-zero")

    def evaluate(self, initial, previous, current, environment) -> TerminationEvent | None:
        """Detects when the accumulated turn reaches the configured signed target.
        
        Returns:
        	TerminationEvent: The event at the interpolated crossing point, or `None` if the target is not reached.
        """
        target = self.turn_rad
        crossed = (
            target > 0.0 and previous.accumulated_turn_rad <= target <= current.accumulated_turn_rad
        ) or (
            target < 0.0 and previous.accumulated_turn_rad >= target >= current.accumulated_turn_rad
        )
        if crossed:
            return TerminationEvent(
                "accumulated_turn",
                self.role,
                _crossing_fraction(previous.accumulated_turn_rad, current.accumulated_turn_rad, target),
                f"Accumulated turn reached {target:g} rad",
            )
        return None


@dataclass(frozen=True, slots=True)
class HeadingWithin:
    target_heading_true_rad: float
    tolerance_rad: float
    role: TerminationRole = TerminationRole.GOAL

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.target_heading_true_rad)):
            raise ValidationError("target heading must be finite")
        if not math.isfinite(float(self.tolerance_rad)) or self.tolerance_rad < 0.0:
            raise ValidationError("heading tolerance must be finite and non-negative")

    def evaluate(self, initial, previous, current, environment) -> TerminationEvent | None:
        """
        Determine whether the current heading is within the configured angular tolerance.
        
        Parameters:
            current: The current simulation state used to evaluate the heading.
            environment: The simulation environment associated with the evaluation.
        
        Returns:
            TerminationEvent | None: An event at the end of the step if the heading is within tolerance; otherwise, `None`.
        """
        if abs(signed_angle_difference_rad(self.target_heading_true_rad, current.heading_true_rad)) <= self.tolerance_rad:
            return TerminationEvent(
                "heading_within",
                self.role,
                1.0,
                "Target heading tolerance reached",
            )
        return None


@dataclass(frozen=True, slots=True)
class AnyOf:
    conditions: tuple[TerminationCondition, ...]

    def __post_init__(self) -> None:
        """Normalize the termination conditions and require at least one condition."""
        object.__setattr__(self, "conditions", tuple(self.conditions))
        if not self.conditions:
            raise ValidationError("AnyOf requires at least one condition")

    def evaluate(self, initial, previous, current, environment) -> TerminationEvent | None:
        """
        Selects the earliest termination event produced by the configured conditions.
        
        Parameters:
            initial: The initial simulation state.
            previous: The state at the start of the current step.
            current: The state at the end of the current step.
            environment: The simulation environment used to evaluate conditions.
        
        Returns:
            The earliest termination event, with safety events taking precedence over goal
            and phase-exit events when events occur at the same step fraction, or `None`
            if no condition is met.
        """
        events = [
            event
            for condition in self.conditions
            if (event := condition.evaluate(initial, previous, current, environment)) is not None
        ]
        if not events:
            return None
        role_order = {TerminationRole.SAFETY: 0, TerminationRole.GOAL: 1, TerminationRole.PHASE_EXIT: 2}
        return min(events, key=lambda event: (event.fraction_of_step, role_order[event.role]))
