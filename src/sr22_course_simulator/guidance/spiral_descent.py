"""Minimal, bounded Spiral Descent path/procedure guidance.

Procedure values are extracted only from :class:`ManeuverSpec`.  Controller
gains, the TAS interpretation, trim Pitch and established Power are explicit
assumptions supplied in :class:`SpiralGuidanceConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math

from sr22_course_simulator.aircraft.input import FlapSetting, FlightInput
from sr22_course_simulator.aircraft.model import AircraftResponseModel
from sr22_course_simulator.aircraft.state import AirspeedKind, AircraftState, GeoPosition, InitialState
from sr22_course_simulator.environment import Environment
from sr22_course_simulator.errors import UnsupportedModelError, ValidationError
from sr22_course_simulator.guidance.wind_correction import solve_heading_for_ground_track
from sr22_course_simulator.maneuver.spec import LimitDirection, ManeuverSpec
from sr22_course_simulator.path.reference import PylonSpiralPath
from sr22_course_simulator.provenance import EvidenceKind
from sr22_course_simulator.simulation.integrator import (
    ForwardSimulator,
    SimulationConfig,
    SimulationProgress,
)
from sr22_course_simulator.simulation.termination import (
    AccumulatedTurn,
    AltitudeAglAtOrBelow,
    AnyOf,
    TerminationCondition,
)
from sr22_course_simulator.simulation.trajectory import SimulationResult
from sr22_course_simulator.units import (
    degrees_to_radians,
    feet_to_metres,
    knots_to_metres_per_second,
    signed_angle_difference_rad,
    wrap_radians_2pi,
)


@dataclass(frozen=True, slots=True)
class SpiralGuidanceConfig:
    """Explicit non-procedure assumptions used by the minimal controller."""

    interpret_unspecified_airspeed_as_tas: bool
    entry_duration_s: float
    established_power_fraction: float
    trim_pitch_rad: float
    speed_error_to_pitch_gain_rad_per_mps: float
    heading_error_to_bank_gain: float
    radial_error_gain_per_m: float
    maximum_intercept_angle_rad: float
    flap: FlapSetting

    def __post_init__(self) -> None:
        if not isinstance(self.interpret_unspecified_airspeed_as_tas, bool):
            raise ValidationError("interpret_unspecified_airspeed_as_tas must be bool")
        finite = (
            self.entry_duration_s,
            self.established_power_fraction,
            self.trim_pitch_rad,
            self.speed_error_to_pitch_gain_rad_per_mps,
            self.heading_error_to_bank_gain,
            self.radial_error_gain_per_m,
            self.maximum_intercept_angle_rad,
        )
        if any(not math.isfinite(float(value)) for value in finite):
            raise ValidationError("guidance configuration values must be finite")
        if self.entry_duration_s < 0.0:
            raise ValidationError("entry_duration_s must be non-negative")
        if not 0.0 <= self.established_power_fraction <= 1.0:
            raise ValidationError("established_power_fraction must be in [0, 1]")
        if self.speed_error_to_pitch_gain_rad_per_mps < 0.0:
            raise ValidationError("speed-to-Pitch gain must be non-negative")
        if self.heading_error_to_bank_gain < 0.0 or self.radial_error_gain_per_m < 0.0:
            raise ValidationError("path-guidance gains must be non-negative")
        if not 0.0 <= self.maximum_intercept_angle_rad < math.pi / 2:
            raise ValidationError("maximum intercept angle must be in [0, pi/2)")
        if not isinstance(self.flap, FlapSetting):
            raise ValidationError("flap must be a FlapSetting")


@dataclass(frozen=True, slots=True)
class GuidanceRecord:
    time_s: float
    phase: str
    flight_input: FlightInput
    radial_error_m: float
    desired_track_true_rad: float
    required_heading_true_rad: float
    speed_error_mps: float
    evidence: tuple[EvidenceKind, ...]


@dataclass(frozen=True, slots=True)
class GuidedSimulationResult:
    simulation: SimulationResult
    reference_path: PylonSpiralPath
    maneuver_spec: ManeuverSpec
    guidance_history: tuple[GuidanceRecord, ...]


@dataclass(slots=True)
class SpiralDescentGuidance:
    """A small assumption-labeled controller that consumes narrative semantics."""

    maneuver_spec: ManeuverSpec
    reference_path: PylonSpiralPath
    config: SpiralGuidanceConfig
    _history: list[GuidanceRecord] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """
        Validate the maneuver specification required for Spiral Descent guidance.
        
        Raises:
            ValidationError: If the maneuver is not a Spiral Descent or lacks the
                required entry airspeed, entry power, nominal bank, or maximum bank
                semantics.
        """
        if self.maneuver_spec.name != "Spiral Descent":
            raise ValidationError("SpiralDescentGuidance requires the Spiral Descent ManeuverSpec")
        # Extract every procedure number by semantic role, never from AdvisoryReference.
        entry = self.maneuver_spec.phase("entry")
        execution = self.maneuver_spec.phase("execution")
        if not any(item.quantity == "airspeed_at_pylon_abeam" for item in entry.targets):
            raise ValidationError("Spiral Descent spec lacks its entry airspeed target")
        if not any(item.quantity == "power" for item in entry.initial_settings):
            raise ValidationError("Spiral Descent spec lacks its entry Power initial setting")
        if not any(item.quantity == "bank" for item in execution.nominals):
            raise ValidationError("Spiral Descent spec lacks nominal Bank")
        if not any(item.quantity == "absolute_bank" for item in execution.limits):
            raise ValidationError("Spiral Descent spec lacks maximum Bank")

    @property
    def history(self) -> tuple[GuidanceRecord, ...]:
        """Return the immutable sequence of guidance records generated by the controller.
        
        Returns:
            tuple[GuidanceRecord, ...]: The recorded guidance history.
        """
        return tuple(self._history)

    def reset(self) -> None:
        """Clear all recorded guidance history."""
        self._history.clear()

    def _target_tas_mps(self) -> float:
        """
        Extracts the entry airspeed target as true airspeed in metres per second.
        
        Returns:
        	float: The target true airspeed in metres per second.
        
        Raises:
        	UnsupportedModelError: If the target uses an unsupported unit or its
        		airspeed kind cannot be interpreted as true airspeed.
        """
        target = next(
            item
            for item in self.maneuver_spec.phase("entry").targets
            if item.quantity == "airspeed_at_pylon_abeam"
        )
        if target.unit != "kt":
            raise UnsupportedModelError(f"unsupported procedure airspeed unit: {target.unit}")
        if target.airspeed_kind is AirspeedKind.TRUE:
            return knots_to_metres_per_second(target.value)
        if target.airspeed_kind is AirspeedKind.UNSPECIFIED and self.config.interpret_unspecified_airspeed_as_tas:
            return knots_to_metres_per_second(target.value)
        raise UnsupportedModelError(
            "The procedure airspeed cannot be used as TAS without an explicit interpretation/conversion model",
            gap="110 kt airspeed kind is unverified in the available source summary",
        )

    def _entry_power_fraction(self) -> float:
        """Return the entry power setting as a fraction of full power.
        
        Returns:
        	float: The entry power setting divided by 100.
        
        Raises:
        	UnsupportedModelError: If the entry power setting uses a unit other than percent.
        """
        setting = next(
            item
            for item in self.maneuver_spec.phase("entry").initial_settings
            if item.quantity == "power"
        )
        if setting.unit != "percent":
            raise UnsupportedModelError(f"unsupported procedure Power unit: {setting.unit}")
        return setting.value / 100.0

    def _banks_rad(self) -> tuple[float, float]:
        execution = self.maneuver_spec.phase("execution")
        nominal = next(item for item in execution.nominals if item.quantity == "bank")
        limit = next(item for item in execution.limits if item.quantity == "absolute_bank")
        if nominal.unit != "deg" or limit.unit != "deg" or limit.direction is not LimitDirection.MAXIMUM:
            raise UnsupportedModelError("unsupported Bank semantics in Spiral Descent spec")
        return degrees_to_radians(nominal.value), degrees_to_radians(limit.value)

    def _command(
        self,
        *,
        position: GeoPosition,
        altitude_m: float,
        heading_true_rad: float,
        true_airspeed_mps: float,
        time_s: float,
        elapsed_s: float,
        environment: Environment,
    ) -> FlightInput:
        """
        Compute a bounded flight command for tracking the spiral descent path.
        
        Parameters:
            position (GeoPosition): Current aircraft position.
            altitude_m (float): Current altitude in meters.
            heading_true_rad (float): Current true heading in radians.
            true_airspeed_mps (float): Current true airspeed in meters per second.
            time_s (float): Current simulation time in seconds.
            elapsed_s (float): Elapsed time since maneuver initiation in seconds.
            environment (Environment): Atmospheric environment used for wind correction.
        
        Returns:
            FlightInput: The commanded pitch, bank, power, and flap settings.
        """
        target_tas = self._target_tas_mps()
        nominal_bank, maximum_bank = self._banks_rad()
        projection = self.reference_path.project(position)

        # Tangent plus an inward/outward cross-track correction; path geometry is
        # never modified.  The gain and intercept bound are explicit assumptions.
        bearing = projection.bearing_from_center_rad
        direction = self.reference_path.turn_direction
        tangent_east = direction * math.cos(bearing)
        tangent_north = -direction * math.sin(bearing)
        radial_east = math.sin(bearing)
        radial_north = math.cos(bearing)
        correction = max(
            -math.tan(self.config.maximum_intercept_angle_rad),
            min(
                math.tan(self.config.maximum_intercept_angle_rad),
                self.config.radial_error_gain_per_m * projection.radial_error_m,
            ),
        )
        desired_east = tangent_east - correction * radial_east
        desired_north = tangent_north - correction * radial_north
        desired_track = wrap_radians_2pi(math.atan2(desired_east, desired_north))
        wind = environment.wind.velocity_at(position, altitude_m, time_s)
        wind_solution = solve_heading_for_ground_track(
            desired_track_true_rad=desired_track,
            true_airspeed_mps=max(true_airspeed_mps, 1e-9),
            wind=wind,
        )
        heading_error = signed_angle_difference_rad(
            wind_solution.required_heading_true_rad,
            heading_true_rad,
        )
        signed_nominal = direction * nominal_bank
        bank = signed_nominal + self.config.heading_error_to_bank_gain * heading_error
        bank = max(-maximum_bank, min(maximum_bank, bank))

        speed_error = true_airspeed_mps - target_tas
        pitch = self.config.trim_pitch_rad + self.config.speed_error_to_pitch_gain_rad_per_mps * speed_error
        phase = "entry" if elapsed_s < self.config.entry_duration_s else "execution"
        power = self._entry_power_fraction() if phase == "entry" else self.config.established_power_fraction
        command = FlightInput(pitch, bank, power, self.config.flap)
        self._history.append(
            GuidanceRecord(
                time_s=time_s,
                phase=phase,
                flight_input=command,
                radial_error_m=projection.radial_error_m,
                desired_track_true_rad=desired_track,
                required_heading_true_rad=wind_solution.required_heading_true_rad,
                speed_error_mps=speed_error,
                evidence=(
                    EvidenceKind.PROCEDURE_TARGET,
                    EvidenceKind.PROCEDURE_NOMINAL,
                    EvidenceKind.PROCEDURE_LIMIT,
                    EvidenceKind.PROCEDURE_CONTROL_RELATIONSHIP,
                    EvidenceKind.PHYSICS_DERIVED,
                    EvidenceKind.ASSUMED,
                ),
            )
        )
        return command

    def initial_input(self, initial: InitialState, environment: Environment) -> FlightInput:
        """Generate the initial flight command from the aircraft state and environment."""
        return self._command(
            position=initial.position,
            altitude_m=initial.altitude_m,
            heading_true_rad=initial.heading_true_rad,
            true_airspeed_mps=initial.true_airspeed_mps,
            time_s=initial.time_s,
            elapsed_s=0.0,
            environment=environment,
        )

    def input_at(self, state: AircraftState, progress: SimulationProgress, environment: Environment) -> FlightInput:
        """
        Generate flight inputs for the current simulation state and elapsed maneuver time.
        
        Parameters:
        	state (AircraftState): Current aircraft state.
        	progress (SimulationProgress): Simulation progress containing elapsed maneuver time.
        	environment (Environment): Current flight environment.
        
        Returns:
        	FlightInput: Guidance command for the current state and environment.
        """
        return self._command(
            position=state.position,
            altitude_m=state.altitude_m,
            heading_true_rad=state.heading_true_rad,
            true_airspeed_mps=state.true_airspeed_mps,
            time_s=state.time_s,
            elapsed_s=progress.elapsed_s,
            environment=environment,
        )


def simulate_guided_spiral_descent(
    *,
    initial: InitialState,
    environment: Environment,
    maneuver_spec: ManeuverSpec,
    reference_path: PylonSpiralPath,
    guidance_config: SpiralGuidanceConfig,
    aircraft_model: AircraftResponseModel,
    termination: TerminationCondition | None,
    simulation_config: SimulationConfig,
) -> GuidedSimulationResult:
    """
    Run a guided Spiral Descent simulation with the procedural minimum-AGL safety stop.
    
    Parameters:
    	initial (InitialState): Initial aircraft state.
    	environment (Environment): Simulation environment.
    	maneuver_spec (ManeuverSpec): Maneuver definition containing safety and termination requirements.
    	reference_path (PylonSpiralPath): Spiral path to follow.
    	guidance_config (SpiralGuidanceConfig): Guidance controller configuration.
    	aircraft_model (AircraftResponseModel): Aircraft response model.
    	termination (TerminationCondition | None): Optional termination condition; when omitted, the accumulated-turn condition is read from the maneuver specification.
    	simulation_config (SimulationConfig): Simulation settings.
    
    Returns:
    	GuidedSimulationResult: Simulation output, reference path, maneuver specification, and immutable guidance history.
    
    Raises:
    	UnsupportedModelError: If the maneuver lacks a supported minimum-AGL constraint or required accumulated-turn termination condition.
    """

    minimum_agl = next(
        (
            constraint
            for constraint in maneuver_spec.safety_constraints
            if constraint.quantity == "minimum_training_height" and constraint.reference == "AGL"
        ),
        None,
    )
    if minimum_agl is None or minimum_agl.unit != "ft":
        raise UnsupportedModelError("Spiral Descent minimum AGL constraint is missing or unsupported")
    safety = AltitudeAglAtOrBelow(feet_to_metres(minimum_agl.value))
    if termination is None:
        completion = next(
            (
                item
                for item in maneuver_spec.termination_conditions
                if item.quantity == "accumulated_turn" and item.value is not None
            ),
            None,
        )
        if completion is None or completion.unit != "deg":
            raise UnsupportedModelError("Spiral Descent accumulated-turn termination is missing")
        termination = AccumulatedTurn(
            reference_path.turn_direction * degrees_to_radians(completion.value)
        )
    combined_termination = AnyOf((termination, safety))
    guidance = SpiralDescentGuidance(maneuver_spec, reference_path, guidance_config)
    guidance.reset()
    simulation = ForwardSimulator().simulate(
        initial=initial,
        environment=environment,
        input_source=guidance,
        aircraft_model=aircraft_model,
        termination=combined_termination,
        config=simulation_config,
    )
    simulation = replace(
        simulation,
        mode="maneuver_guidance",
        notes=(
            *simulation.notes,
            f"Minimum implementation stops at {minimum_agl.value:g} {minimum_agl.unit} AGL; "
            "the source contingency to hold altitude and continue to the prescribed heading "
            "is not yet simulated.",
            "Recovery after rollout is encoded in ManeuverSpec but not propagated by this guidance run.",
        ),
    )
    return GuidedSimulationResult(
        simulation=simulation,
        reference_path=reference_path,
        maneuver_spec=maneuver_spec,
        guidance_history=guidance.history,
    )
