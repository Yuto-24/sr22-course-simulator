"""Fixed-step quasi-steady forward propagation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from sr22_course_simulator.aircraft.input import FlightInput
from sr22_course_simulator.aircraft.loading import FuelState
from sr22_course_simulator.aircraft.model import AircraftResponseModel, QuasiSteadyResponse
from sr22_course_simulator.aircraft.state import AircraftState, InitialState
from sr22_course_simulator.environment import Environment
from sr22_course_simulator.errors import UnsupportedModelError, ValidationError
from sr22_course_simulator.geometry import displace_position, enu_displacement
from sr22_course_simulator.provenance import EvidenceKind
from sr22_course_simulator.simulation.physics import (
    VelocityENU,
    add_wind,
    air_velocity_enu,
    coordinated_turn_rate_rad_s,
)
from sr22_course_simulator.simulation.termination import TerminationCondition, TerminationEvent, TerminationRole
from sr22_course_simulator.simulation.trajectory import SimulationOutcome, SimulationResult, Trajectory
from sr22_course_simulator.units import signed_angle_difference_rad, wrap_radians_2pi


@dataclass(frozen=True, slots=True)
class SimulationProgress:
    step: int
    elapsed_s: float
    accumulated_turn_rad: float


@runtime_checkable
class FlightInputSource(Protocol):
    def initial_input(self, initial: InitialState, environment: Environment) -> FlightInput:
        ...

    def input_at(
        self,
        state: AircraftState,
        progress: SimulationProgress,
        environment: Environment,
    ) -> FlightInput:
        ...


@dataclass(frozen=True, slots=True)
class ConstantFlightInput:
    flight_input: FlightInput

    def initial_input(self, initial: InitialState, environment: Environment) -> FlightInput:
        return self.flight_input

    def input_at(self, state, progress, environment) -> FlightInput:
        return self.flight_input


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    dt_s: float
    max_steps: int

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.dt_s)) or self.dt_s <= 0.0:
            raise ValidationError("dt_s must be finite and positive")
        if isinstance(self.max_steps, bool) or self.max_steps <= 0:
            raise ValidationError("max_steps must be a positive integer")


def _seed_state(initial: InitialState, flight_input: FlightInput) -> AircraftState:
    """Internal-only state used to query the model before derived state exists."""

    return AircraftState(
        time_s=initial.time_s,
        position=initial.position,
        altitude_m=initial.altitude_m,
        heading_true_rad=initial.heading_true_rad,
        track_true_rad=initial.heading_true_rad,
        true_airspeed_mps=initial.true_airspeed_mps,
        ground_speed_mps=initial.true_airspeed_mps,
        vertical_speed_mps=0.0,
        pitch_rad=flight_input.pitch_rad,
        bank_rad=flight_input.bank_rad,
        power_fraction=flight_input.power_fraction,
        flap=flight_input.flap,
        fuel_remaining_kg=initial.initial_fuel_mass_kg,
        fuel_burned_kg=0.0,
        weight_kg=initial.initial_weight_kg,
        accumulated_turn_rad=0.0,
        evidence=(),
        source_citations=(),
    )


def _resolve_ground_track(
    ground_velocity: VelocityENU,
    *,
    previous_track_true_rad: float | None,
) -> float:
    """Resolve track without assigning a direction to zero ground velocity.

    Once the trajectory has established a valid track, an exact horizontal
    velocity cancellation preserves that last track as state history.  At the
    initial state there is no valid track to preserve, so the operating point
    is explicitly unsupported.
    """

    track = ground_velocity.track_true_rad_or_none
    if track is not None:
        return track
    if previous_track_true_rad is not None:
        return previous_track_true_rad
    raise UnsupportedModelError(
        "Initial ground track is undefined at zero horizontal ground speed",
        gap="A non-zero horizontal ground velocity is required to establish initial track",
    )


def _state_at_initial(
    initial: InitialState,
    flight_input: FlightInput,
    response: QuasiSteadyResponse,
    environment: Environment,
) -> AircraftState:
    air = air_velocity_enu(
        true_airspeed_mps=response.true_airspeed_mps,
        heading_true_rad=initial.heading_true_rad,
        flight_path_angle_rad=response.flight_path_angle_rad,
    )
    ground = add_wind(
        air,
        environment.wind.velocity_at(initial.position, initial.altitude_m, initial.time_s),
    )
    track_true_rad = _resolve_ground_track(ground, previous_track_true_rad=None)
    return AircraftState(
        time_s=initial.time_s,
        position=initial.position,
        altitude_m=initial.altitude_m,
        heading_true_rad=initial.heading_true_rad,
        track_true_rad=track_true_rad,
        true_airspeed_mps=response.true_airspeed_mps,
        ground_speed_mps=ground.horizontal_speed_mps,
        vertical_speed_mps=ground.up_mps,
        pitch_rad=flight_input.pitch_rad,
        bank_rad=flight_input.bank_rad,
        power_fraction=flight_input.power_fraction,
        flap=flight_input.flap,
        fuel_remaining_kg=initial.initial_fuel_mass_kg,
        fuel_burned_kg=0.0,
        weight_kg=initial.initial_weight_kg,
        accumulated_turn_rad=0.0,
        evidence=response.evidence + (EvidenceKind.PHYSICS_DERIVED,),
        source_citations=response.source_citations,
    )


def _advance(
    *,
    initial: InitialState,
    current: AircraftState,
    flight_input: FlightInput,
    response: QuasiSteadyResponse,
    environment: Environment,
    dt_s: float,
) -> AircraftState:
    turn_rate = coordinated_turn_rate_rad_s(response.true_airspeed_mps, flight_input.bank_rad)
    heading_delta = turn_rate * dt_s
    midpoint_heading = current.heading_true_rad + 0.5 * heading_delta
    air = air_velocity_enu(
        true_airspeed_mps=response.true_airspeed_mps,
        heading_true_rad=midpoint_heading,
        flight_path_angle_rad=response.flight_path_angle_rad,
    )
    wind = environment.wind.velocity_at(current.position, current.altitude_m, current.time_s + 0.5 * dt_s)
    ground = add_wind(air, wind)
    track_true_rad = _resolve_ground_track(
        ground,
        previous_track_true_rad=current.track_true_rad,
    )
    next_position = displace_position(
        current.position,
        east_m=ground.east_mps * dt_s,
        north_m=ground.north_mps * dt_s,
    )
    fuel = FuelState(initial.initial_fuel_mass_kg, current.fuel_remaining_kg).burn(
        fuel_flow_kg_s=response.fuel_flow_kg_s,
        dt_s=dt_s,
    )
    return AircraftState(
        time_s=current.time_s + dt_s,
        position=next_position,
        altitude_m=current.altitude_m + ground.up_mps * dt_s,
        heading_true_rad=current.heading_true_rad + heading_delta,
        track_true_rad=track_true_rad,
        true_airspeed_mps=response.true_airspeed_mps,
        ground_speed_mps=ground.horizontal_speed_mps,
        vertical_speed_mps=ground.up_mps,
        pitch_rad=flight_input.pitch_rad,
        bank_rad=flight_input.bank_rad,
        power_fraction=flight_input.power_fraction,
        flap=flight_input.flap,
        fuel_remaining_kg=fuel.remaining_mass_kg,
        fuel_burned_kg=fuel.burned_mass_kg,
        weight_kg=initial.loading.gross_mass_kg(fuel.remaining_mass_kg),
        accumulated_turn_rad=current.accumulated_turn_rad + heading_delta,
        evidence=response.evidence + (EvidenceKind.PHYSICS_DERIVED,),
        source_citations=response.source_citations,
    )


def _linear(a: float, b: float, fraction: float) -> float:
    return a + (b - a) * fraction


def interpolate_state(previous: AircraftState, current: AircraftState, fraction: float) -> AircraftState:
    """Interpolate a threshold-crossing state without overshooting a safety stop."""

    if fraction <= 0.0:
        return previous
    if fraction >= 1.0:
        return current
    east, north = enu_displacement(previous.position, current.position)
    position = displace_position(previous.position, east_m=east * fraction, north_m=north * fraction)
    heading_delta = current.accumulated_turn_rad - previous.accumulated_turn_rad
    track_delta = signed_angle_difference_rad(current.track_true_rad, previous.track_true_rad)
    return AircraftState(
        time_s=_linear(previous.time_s, current.time_s, fraction),
        position=position,
        altitude_m=_linear(previous.altitude_m, current.altitude_m, fraction),
        heading_true_rad=wrap_radians_2pi(previous.heading_true_rad + heading_delta * fraction),
        track_true_rad=wrap_radians_2pi(previous.track_true_rad + track_delta * fraction),
        true_airspeed_mps=_linear(previous.true_airspeed_mps, current.true_airspeed_mps, fraction),
        ground_speed_mps=_linear(previous.ground_speed_mps, current.ground_speed_mps, fraction),
        vertical_speed_mps=_linear(previous.vertical_speed_mps, current.vertical_speed_mps, fraction),
        pitch_rad=_linear(previous.pitch_rad, current.pitch_rad, fraction),
        bank_rad=_linear(previous.bank_rad, current.bank_rad, fraction),
        power_fraction=_linear(previous.power_fraction, current.power_fraction, fraction),
        flap=current.flap,
        fuel_remaining_kg=_linear(previous.fuel_remaining_kg, current.fuel_remaining_kg, fraction),
        fuel_burned_kg=_linear(previous.fuel_burned_kg, current.fuel_burned_kg, fraction),
        weight_kg=_linear(previous.weight_kg, current.weight_kg, fraction),
        accumulated_turn_rad=_linear(
            previous.accumulated_turn_rad,
            current.accumulated_turn_rad,
            fraction,
        ),
        evidence=tuple(dict.fromkeys(previous.evidence + current.evidence)),
        source_citations=tuple(
            dict.fromkeys(previous.source_citations + current.source_citations)
        ),
    )


class ForwardSimulator:
    """Propagate direct Pitch/Bank/PWR/Flap inputs; no maneuver spec is accepted."""

    def simulate(
        self,
        *,
        initial: InitialState,
        environment: Environment,
        input_source: FlightInputSource,
        aircraft_model: AircraftResponseModel,
        termination: TerminationCondition,
        config: SimulationConfig,
    ) -> SimulationResult:
        first_input = input_source.initial_input(initial, environment)
        seed = _seed_state(initial, first_input)
        first_response = aircraft_model.resolve(seed, first_input, environment)
        current = _state_at_initial(initial, first_input, first_response, environment)
        states = [current]

        # Evaluate zero-duration/initially-met conditions through a degenerate pair.
        initial_event = termination.evaluate(initial, current, current, environment)
        if initial_event is not None:
            outcome = (
                SimulationOutcome.SAFETY_STOP
                if initial_event.role is TerminationRole.SAFETY
                else SimulationOutcome.GOAL_REACHED
            )
            return SimulationResult(
                trajectory=Trajectory(tuple(states)),
                outcome=outcome,
                termination_event=initial_event,
                model_name=aircraft_model.name,
                mode="forward",
                notes=first_response.notes,
            )

        for step in range(config.max_steps):
            progress = SimulationProgress(
                step=step,
                elapsed_s=current.time_s - initial.time_s,
                accumulated_turn_rad=current.accumulated_turn_rad,
            )
            command = input_source.input_at(current, progress, environment)
            response = aircraft_model.resolve(current, command, environment)
            candidate = _advance(
                initial=initial,
                current=current,
                flight_input=command,
                response=response,
                environment=environment,
                dt_s=config.dt_s,
            )
            event = termination.evaluate(initial, current, candidate, environment)
            if event is not None:
                final_state = interpolate_state(current, candidate, event.fraction_of_step)
                if final_state.time_s > states[-1].time_s:
                    states.append(final_state)
                outcome = (
                    SimulationOutcome.SAFETY_STOP
                    if event.role is TerminationRole.SAFETY
                    else SimulationOutcome.GOAL_REACHED
                )
                return SimulationResult(
                    trajectory=Trajectory(tuple(states)),
                    outcome=outcome,
                    termination_event=event,
                    model_name=aircraft_model.name,
                    mode="forward",
                    notes=tuple(dict.fromkeys(first_response.notes + response.notes)),
                )
            states.append(candidate)
            current = candidate

        return SimulationResult(
            trajectory=Trajectory(tuple(states)),
            outcome=SimulationOutcome.MAX_STEPS,
            termination_event=None,
            model_name=aircraft_model.name,
            mode="forward",
            notes=("Maximum integration-step guard reached before a termination condition.",),
        )


def simulate_forward(**kwargs) -> SimulationResult:
    """Functional convenience wrapper around :class:`ForwardSimulator`."""

    return ForwardSimulator().simulate(**kwargs)
