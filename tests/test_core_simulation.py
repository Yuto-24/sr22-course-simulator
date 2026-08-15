"""Deterministic tests for units, wind, analytical physics, and propagation.

The numerical fixture in this module is deliberately an explicit assumption
model.  It supplies a constant local TAS/fuel-flow operating point and the
documented fixed-angle-of-attack closure; it is not presented as SR22 POH data.
"""

from __future__ import annotations

import math
import unittest

from sr22_course_simulator.aircraft import (
    AssumedAngleOfAttackClosure,
    AssumedSteadyPointProvider,
    AssumptionDomain,
    FlapSetting,
    FlightInput,
    GeoPosition,
    InitialState,
    Loading,
    MassItem,
    QuasiSteadyAircraftModel,
    SourceDataRequiredPerformanceProvider,
)
from sr22_course_simulator.environment import (
    Atmosphere,
    ConstantWind,
    Environment,
    NoWind,
    WindVector,
)
from sr22_course_simulator.errors import UnsupportedModelError, ValidationError
from sr22_course_simulator.geometry import enu_displacement
from sr22_course_simulator.provenance import EvidenceKind
from sr22_course_simulator.simulation import (
    AccumulatedTurn,
    AltitudeAtOrBelow,
    ConstantFlightInput,
    ElapsedTime,
    SimulationConfig,
    SimulationOutcome,
    coordinated_load_factor,
    coordinated_turn_radius_m,
    coordinated_turn_rate_rad_s,
    simulate_forward,
)
from sr22_course_simulator.units import (
    degrees_to_radians,
    feet_to_metres,
    knots_to_metres_per_second,
    metres_to_feet,
    metres_to_nautical_miles,
    metres_per_second_to_knots,
    nautical_miles_to_metres,
    radians_to_degrees,
    wrap_degrees_360,
    wrap_radians_2pi,
)


class CoreSimulationTestCase(unittest.TestCase):
    """Shared, intentionally narrow direct-simulation fixtures."""

    ORIGIN = GeoPosition(latitude_deg=35.0, longitude_deg=135.0)
    TAS_MPS = 50.0
    POWER_FRACTION = 0.5

    def make_environment(self, wind=None) -> Environment:
        """
        Create a standard sea-level simulation environment with the specified wind model.
        
        Parameters:
        	wind: Optional wind model; uses calm conditions when omitted.
        
        Returns:
        	Environment: An environment with standard sea-level atmospheric conditions and the selected wind model.
        """
        return Environment(
            atmosphere=Atmosphere(temperature_k=288.15, pressure_altitude_m=0.0),
            wind=NoWind() if wind is None else wind,
        )

    def make_initial(
        self,
        *,
        altitude_m: float = 1_000.0,
        heading_rad: float = 0.0,
        fuel_mass_kg: float = 40.0,
        time_s: float = 0.0,
        tas_mps: float = TAS_MPS,
    ) -> InitialState:
        """
        Create an initial aircraft state with configurable flight conditions and loading.
        
        Parameters:
        	altitude_m (float): Initial altitude in metres.
        	heading_rad (float): Initial true heading in radians.
        	fuel_mass_kg (float): Initial fuel mass in kilograms.
        	time_s (float): Initial simulation time in seconds.
        	tas_mps (float): Initial true airspeed in metres per second.
        
        Returns:
        	InitialState: The initialized aircraft state.
        """
        return InitialState(
            time_s=time_s,
            position=self.ORIGIN,
            altitude_m=altitude_m,
            heading_true_rad=heading_rad,
            true_airspeed_mps=tas_mps,
            loading=Loading(
                empty_aircraft_mass_kg=1_000.0,
                payload=(MassItem("occupants and baggage", 100.0),),
            ),
            initial_fuel_mass_kg=fuel_mass_kg,
        )

    def make_model(
        self,
        *,
        tas_mps: float = TAS_MPS,
        fuel_flow_kg_s: float = 0.0,
        reference_angle_of_attack_rad: float = 0.0,
        maximum_bank_rad: float = math.radians(70.0),
        tas_per_power_fraction_mps: float = 0.0,
    ) -> QuasiSteadyAircraftModel:
        """
        Create an assumed steady-point aircraft model for deterministic tests.
        
        Parameters:
            tas_mps (float): Reference true airspeed.
            fuel_flow_kg_s (float): Fuel flow at zero power.
            reference_angle_of_attack_rad (float): Angle of attack used by the longitudinal closure.
            maximum_bank_rad (float): Maximum absolute bank angle supported by the model.
            tas_per_power_fraction_mps (float): True-airspeed change per unit power fraction.
        
        Returns:
            QuasiSteadyAircraftModel: A test-only aircraft model with fixed flap support and bounded pitch, bank, and power assumptions.
        """
        domain = AssumptionDomain(
            minimum_pitch_rad=math.radians(-30.0),
            maximum_pitch_rad=math.radians(30.0),
            minimum_bank_rad=-maximum_bank_rad,
            maximum_bank_rad=maximum_bank_rad,
            minimum_power_fraction=0.0,
            maximum_power_fraction=1.0,
            supported_flaps=(FlapSetting.RETRACTED,),
        )
        performance = AssumedSteadyPointProvider(
            domain=domain,
            reference_true_airspeed_mps=tas_mps,
            reference_power_fraction=self.POWER_FRACTION,
            reference_pitch_rad=0.0,
            tas_per_power_fraction_mps=tas_per_power_fraction_mps,
            tas_per_pitch_rad_mps=0.0,
            zero_power_fuel_flow_kg_s=fuel_flow_kg_s,
            fuel_flow_per_power_fraction_kg_s=0.0,
        )
        return QuasiSteadyAircraftModel(
            name="test-only explicit steady-point assumption",
            performance=performance,
            longitudinal_closure=AssumedAngleOfAttackClosure(
                reference_angle_of_attack_rad=reference_angle_of_attack_rad
            ),
        )

    def make_input(self, *, pitch_rad: float = 0.0, bank_rad: float = 0.0) -> FlightInput:
        """
        Create flight inputs with the specified pitch and bank angles.
        
        Parameters:
            pitch_rad (float): Pitch angle in radians.
            bank_rad (float): Bank angle in radians.
        
        Returns:
            FlightInput: Flight inputs using the fixture's power fraction and retracted flaps.
        """
        return FlightInput(
            pitch_rad=pitch_rad,
            bank_rad=bank_rad,
            power_fraction=self.POWER_FRACTION,
            flap=FlapSetting.RETRACTED,
        )

    def simulate(
        self,
        *,
        termination,
        flight_input: FlightInput | None = None,
        initial: InitialState | None = None,
        environment: Environment | None = None,
        aircraft_model=None,
        dt_s: float = 0.25,
        max_steps: int = 10_000,
    ):
        """
        Run a forward simulation using the supplied or default test fixtures.
        
        Parameters:
        	termination: Condition that ends the simulation.
        	flight_input (FlightInput | None): Flight inputs to use; defaults to the shared fixture inputs.
        	initial (InitialState | None): Initial aircraft state; defaults to the shared fixture state.
        	environment (Environment | None): Simulation environment; defaults to the shared fixture environment.
        	aircraft_model: Aircraft model to simulate; defaults to the shared fixture model.
        	dt_s (float): Simulation time step in seconds.
        	max_steps (int): Maximum number of simulation steps.
        
        Returns:
        	The resulting forward simulation trajectory.
        """
        return simulate_forward(
            initial=self.make_initial() if initial is None else initial,
            environment=self.make_environment() if environment is None else environment,
            input_source=ConstantFlightInput(
                self.make_input() if flight_input is None else flight_input
            ),
            aircraft_model=self.make_model() if aircraft_model is None else aircraft_model,
            termination=termination,
            config=SimulationConfig(dt_s=dt_s, max_steps=max_steps),
        )


class UnitConversionTests(CoreSimulationTestCase):
    def test_aviation_and_si_conversion_boundaries(self) -> None:
        cases = (
            (feet_to_metres(1.0), 0.3048),
            (metres_to_feet(0.3048), 1.0),
            (knots_to_metres_per_second(1.0), 1852.0 / 3600.0),
            (metres_per_second_to_knots(1852.0 / 3600.0), 1.0),
            (nautical_miles_to_metres(1.0), 1852.0),
            (metres_to_nautical_miles(1852.0), 1.0),
            (degrees_to_radians(180.0), math.pi),
            (radians_to_degrees(math.pi), 180.0),
        )
        for actual, expected in cases:
            with self.subTest(expected=expected):
                self.assertAlmostEqual(actual, expected, places=12)

    def test_angle_wrapping_clamps_rounded_upper_bound_to_zero(self) -> None:
        smallest_negative = -math.ulp(0.0)

        wrapped_radians = wrap_radians_2pi(smallest_negative)
        wrapped_degrees = wrap_degrees_360(smallest_negative)

        self.assertEqual(wrapped_radians, 0.0)
        self.assertLess(wrapped_radians, math.tau)
        self.assertEqual(wrapped_degrees, 0.0)
        self.assertLess(wrapped_degrees, 360.0)


class WindTests(CoreSimulationTestCase):
    def test_no_wind_returns_zero_enu_vector(self) -> None:
        vector = NoWind().velocity_at(self.ORIGIN, altitude_m=1_000.0, time_s=123.0)
        self.assertEqual((vector.east_mps, vector.north_mps, vector.up_mps), (0.0, 0.0, 0.0))
        self.assertEqual(vector.horizontal_speed_mps, 0.0)

    def test_meteorological_270_at_20_knots_blows_east(self) -> None:
        expected_speed = knots_to_metres_per_second(20.0)
        vector = ConstantWind.from_meteorological_knots(
            from_direction_deg_true=270.0,
            speed_kt=20.0,
        ).velocity_at(self.ORIGIN, 0.0, 0.0)
        self.assertAlmostEqual(vector.east_mps, expected_speed, places=12)
        self.assertAlmostEqual(vector.north_mps, 0.0, places=12)

    def test_meteorological_000_at_20_knots_blows_south(self) -> None:
        expected_speed = knots_to_metres_per_second(20.0)
        vector = ConstantWind.from_meteorological_knots(
            from_direction_deg_true=0.0,
            speed_kt=20.0,
        ).velocity_at(self.ORIGIN, 0.0, 0.0)
        self.assertAlmostEqual(vector.east_mps, 0.0, places=12)
        self.assertAlmostEqual(vector.north_mps, -expected_speed, places=12)


class AnalyticalTurnTests(CoreSimulationTestCase):
    def test_turn_rate_radius_and_load_factor_match_analytical_equations(self) -> None:
        tas = 50.0
        bank = math.radians(30.0)
        gravity = 9.80665
        expected_rate = gravity * math.tan(bank) / tas
        expected_radius = tas * tas / (gravity * math.tan(bank))
        expected_load_factor = 1.0 / math.cos(bank)

        self.assertAlmostEqual(coordinated_turn_rate_rad_s(tas, bank), expected_rate, places=14)
        self.assertAlmostEqual(coordinated_turn_radius_m(tas, bank), expected_radius, places=12)
        self.assertAlmostEqual(coordinated_load_factor(bank), expected_load_factor, places=14)
        self.assertAlmostEqual(
            coordinated_turn_rate_rad_s(tas, -bank), -expected_rate, places=14
        )
        self.assertAlmostEqual(
            coordinated_turn_radius_m(tas, -bank), -expected_radius, places=12
        )
        self.assertTrue(math.isinf(coordinated_turn_radius_m(tas, 0.0)))


class ForwardPropagationTests(CoreSimulationTestCase):
    def test_initial_termination_preserves_first_response_notes(self) -> None:
        result = self.simulate(termination=ElapsedTime(0.0))

        self.assertEqual(len(result.trajectory), 1)
        self.assertEqual(
            result.notes,
            (
                "Caller-supplied local steady-point relation; not SR22 POH data.",
                "No transient response, bank drag correction, or arbitrary-flight-envelope claim.",
                "Fixed-angle-of-attack longitudinal closure; source or calibration required.",
            ),
        )

    def test_no_wind_zero_bank_flight_is_straight_and_level(self) -> None:
        duration_s = 20.0
        result = self.simulate(termination=ElapsedTime(duration_s), dt_s=0.5)
        east_m, north_m = enu_displacement(self.ORIGIN, result.trajectory.final.position)

        self.assertIs(result.outcome, SimulationOutcome.GOAL_REACHED)
        self.assertAlmostEqual(east_m, 0.0, places=7)
        self.assertAlmostEqual(north_m, self.TAS_MPS * duration_s, places=6)
        self.assertAlmostEqual(result.trajectory.final.altitude_m, 1_000.0, places=12)
        self.assertAlmostEqual(result.trajectory.final.heading_true_rad, 0.0, places=12)
        self.assertAlmostEqual(result.trajectory.final.track_true_rad, 0.0, places=12)
        self.assertAlmostEqual(result.trajectory.final.ground_speed_mps, self.TAS_MPS, places=12)
        self.assertIn(EvidenceKind.ASSUMED, result.trajectory.evidence)
        self.assertIn(EvidenceKind.PHYSICS_DERIVED, result.trajectory.evidence)

    def test_constant_wind_is_added_to_air_relative_velocity(self) -> None:
        duration_s = 10.0
        east_wind_mps = 10.0
        environment = self.make_environment(
            ConstantWind(WindVector(east_mps=east_wind_mps, north_mps=0.0))
        )
        result = self.simulate(
            termination=ElapsedTime(duration_s),
            environment=environment,
            dt_s=0.5,
        )
        east_m, north_m = enu_displacement(self.ORIGIN, result.trajectory.final.position)
        expected_ground_speed = math.hypot(east_wind_mps, self.TAS_MPS)
        expected_track = math.atan2(east_wind_mps, self.TAS_MPS)

        self.assertAlmostEqual(east_m, east_wind_mps * duration_s, delta=0.01)
        self.assertAlmostEqual(north_m, self.TAS_MPS * duration_s, delta=0.01)
        self.assertAlmostEqual(
            result.trajectory.final.ground_speed_mps, expected_ground_speed, places=12
        )
        self.assertAlmostEqual(result.trajectory.final.track_true_rad, expected_track, places=12)
        self.assertAlmostEqual(result.trajectory.final.heading_true_rad, 0.0, places=12)

    def test_exact_later_headwind_cancellation_preserves_last_valid_track(self) -> None:
        initial_input = self.make_input()
        cancellation_input = FlightInput(
            pitch_rad=0.0,
            bank_rad=0.0,
            power_fraction=0.25,
            flap=FlapSetting.RETRACTED,
        )

        class StepInputSource:
            def initial_input(self, initial, environment):
                """
                Provides the initial input for a simulation.
                
                Parameters:
                    initial: Initial aircraft state.
                    environment: Simulation environment.
                
                Returns:
                    The initial simulation input.
                """
                return initial_input

            def input_at(self, state, progress, environment):
                """
                Provide the flight input used at the requested simulation point.
                
                Returns:
                	Flight inputs for the simulation step.
                """
                return cancellation_input

        model = self.make_model(tas_per_power_fraction_mps=40.0)
        environment = self.make_environment(
            ConstantWind(WindVector(east_mps=0.0, north_mps=-40.0))
        )
        initial = self.make_initial()
        result = simulate_forward(
            initial=initial,
            environment=environment,
            input_source=StepInputSource(),
            aircraft_model=model,
            termination=ElapsedTime(1.0),
            config=SimulationConfig(dt_s=1.0, max_steps=2),
        )

        self.assertEqual(result.trajectory.initial.ground_speed_mps, 10.0)
        self.assertEqual(result.trajectory.final.ground_speed_mps, 0.0)
        self.assertEqual(
            result.trajectory.final.track_true_rad,
            result.trajectory.initial.track_true_rad,
        )
        self.assertEqual(result.trajectory.final.position, initial.position)

    def test_constant_bank_calm_turn_matches_circle_and_heading(self) -> None:
        bank_rad = math.radians(30.0)
        rate_rad_s = coordinated_turn_rate_rad_s(self.TAS_MPS, bank_rad)
        radius_m = coordinated_turn_radius_m(self.TAS_MPS, bank_rad)
        half_turn_s = math.pi / rate_rad_s
        result = self.simulate(
            termination=ElapsedTime(half_turn_s),
            flight_input=self.make_input(bank_rad=bank_rad),
            dt_s=0.05,
            max_steps=2_000,
        )
        east_m, north_m = enu_displacement(self.ORIGIN, result.trajectory.final.position)

        self.assertAlmostEqual(result.trajectory.final.heading_true_rad, math.pi, places=11)
        self.assertAlmostEqual(result.trajectory.final.accumulated_turn_rad, math.pi, places=11)
        # The integrator repeatedly maps local EN increments through the
        # documented spherical geographic frame.  Five centimetres over this
        # 883 m half-circle isolates turn/integration regressions without
        # pretending that the composed local-frame mapping is exact Euclidean
        # geometry.
        self.assertAlmostEqual(east_m, 2.0 * radius_m, delta=0.05)
        self.assertAlmostEqual(north_m, 0.0, delta=0.05)

        for state in result.trajectory.states[::50]:
            state_east, state_north = enu_displacement(self.ORIGIN, state.position)
            distance_from_center = math.hypot(state_east - radius_m, state_north)
            self.assertAlmostEqual(distance_from_center, radius_m, delta=0.05)

    def test_known_vertical_component_propagates_altitude(self) -> None:
        air_vertical_mps = -3.0
        vertical_wind_mps = 0.5
        duration_s = 8.0
        pitch_rad = math.asin(air_vertical_mps / self.TAS_MPS)
        environment = self.make_environment(
            ConstantWind(WindVector(east_mps=0.0, north_mps=0.0, up_mps=vertical_wind_mps))
        )
        result = self.simulate(
            termination=ElapsedTime(duration_s),
            flight_input=self.make_input(pitch_rad=pitch_rad),
            environment=environment,
            dt_s=1.5,
        )
        expected_vertical_mps = air_vertical_mps + vertical_wind_mps

        self.assertAlmostEqual(result.trajectory.initial.vertical_speed_mps, expected_vertical_mps)
        self.assertAlmostEqual(result.trajectory.final.vertical_speed_mps, expected_vertical_mps)
        self.assertAlmostEqual(
            result.trajectory.final.altitude_m,
            1_000.0 + expected_vertical_mps * duration_s,
            places=10,
        )

    def test_heading_wraps_while_accumulated_turn_remains_unwrapped(self) -> None:
        initial_heading_rad = math.radians(350.0)
        target_turn_rad = math.radians(30.0)
        bank_rad = math.radians(30.0)
        result = self.simulate(
            initial=self.make_initial(heading_rad=initial_heading_rad),
            termination=AccumulatedTurn(target_turn_rad),
            flight_input=self.make_input(bank_rad=bank_rad),
            dt_s=1.0,
        )

        self.assertAlmostEqual(result.trajectory.final.heading_true_deg, 20.0, places=10)
        self.assertAlmostEqual(
            result.trajectory.final.accumulated_turn_rad, target_turn_rad, places=12
        )
        for state in result.trajectory:
            self.assertGreaterEqual(state.heading_true_rad, 0.0)
            self.assertLess(state.heading_true_rad, math.tau)

    def test_altitude_threshold_is_interpolated_without_overshoot(self) -> None:
        pitch_rad = math.radians(-10.0)
        target_altitude_m = 990.0
        expected_vertical_mps = self.TAS_MPS * math.sin(pitch_rad)
        expected_time_s = (target_altitude_m - 1_000.0) / expected_vertical_mps
        result = self.simulate(
            termination=AltitudeAtOrBelow(target_altitude_m),
            flight_input=self.make_input(pitch_rad=pitch_rad),
            dt_s=1.0,
        )

        self.assertAlmostEqual(result.trajectory.final.altitude_m, target_altitude_m, places=12)
        self.assertAlmostEqual(result.trajectory.final.time_s, expected_time_s, places=12)
        self.assertIsNotNone(result.termination_event)
        assert result.termination_event is not None
        self.assertGreater(result.termination_event.fraction_of_step, 0.0)
        self.assertLess(result.termination_event.fraction_of_step, 1.0)


class FuelAndLoadingTests(CoreSimulationTestCase):
    def test_constant_fuel_flow_is_monotone_and_reduces_weight(self) -> None:
        initial_fuel_kg = 20.0
        flow_kg_s = 0.2
        duration_s = 12.5
        initial = self.make_initial(fuel_mass_kg=initial_fuel_kg)
        model = self.make_model(fuel_flow_kg_s=flow_kg_s)
        result = self.simulate(
            initial=initial,
            aircraft_model=model,
            termination=ElapsedTime(duration_s),
            dt_s=2.0,
        )
        expected_burn_kg = flow_kg_s * duration_s
        remaining = result.trajectory.fuel_remaining_kg

        self.assertTrue(all(later <= earlier for earlier, later in zip(remaining, remaining[1:])))
        self.assertAlmostEqual(result.trajectory.final.fuel_burned_kg, expected_burn_kg, places=12)
        self.assertAlmostEqual(
            result.trajectory.final.fuel_remaining_kg,
            initial_fuel_kg - expected_burn_kg,
            places=12,
        )
        self.assertAlmostEqual(
            result.trajectory.final.weight_kg,
            initial.initial_weight_kg - expected_burn_kg,
            places=12,
        )

    def test_loading_determines_initial_weight(self) -> None:
        loading = Loading(
            empty_aircraft_mass_kg=900.0,
            payload=(MassItem("pilot", 80.0), MassItem("baggage", 20.0)),
        )
        initial = InitialState(
            time_s=0.0,
            position=self.ORIGIN,
            altitude_m=500.0,
            heading_true_rad=math.radians(-10.0),
            true_airspeed_mps=40.0,
            loading=loading,
            initial_fuel_mass_kg=50.0,
        )

        self.assertEqual(loading.non_fuel_mass_kg, 1_000.0)
        self.assertEqual(initial.initial_weight_kg, 1_050.0)
        self.assertAlmostEqual(math.degrees(initial.heading_true_rad), 350.0)

    def test_invalid_loading_and_initial_state_are_rejected(self) -> None:
        with self.subTest("negative empty mass"):
            with self.assertRaises(ValidationError):
                Loading(empty_aircraft_mass_kg=-1.0)
        with self.subTest("negative payload mass"):
            with self.assertRaises(ValidationError):
                MassItem("payload", -1.0)
        with self.subTest("empty payload label"):
            with self.assertRaises(ValidationError):
                MassItem("", 1.0)
        with self.subTest("non-positive initial TAS"):
            with self.assertRaises(ValidationError):
                self.make_initial(tas_mps=0.0)
        with self.subTest("negative initial fuel"):
            with self.assertRaises(ValidationError):
                self.make_initial(fuel_mass_kg=-1.0)


class UnsupportedModelTests(CoreSimulationTestCase):
    def test_exact_initial_headwind_cancellation_is_explicitly_unsupported(self) -> None:
        environment = self.make_environment(
            ConstantWind(WindVector(east_mps=0.0, north_mps=-self.TAS_MPS))
        )

        with self.assertRaises(UnsupportedModelError) as raised:
            self.simulate(
                environment=environment,
                termination=ElapsedTime(1.0),
            )

        self.assertIn("Initial ground track is undefined", str(raised.exception))
        self.assertEqual(
            raised.exception.gap,
            "A non-zero horizontal ground velocity is required to establish initial track",
        )

    def test_missing_source_performance_fails_explicitly(self) -> None:
        required_source = "SR22 approved Chapter 5 performance table"
        model = QuasiSteadyAircraftModel(
            name="source-required test model",
            performance=SourceDataRequiredPerformanceProvider(required_source),
            longitudinal_closure=AssumedAngleOfAttackClosure(0.0),
        )

        with self.assertRaises(UnsupportedModelError) as raised:
            self.simulate(
                aircraft_model=model,
                termination=ElapsedTime(1.0),
            )
        self.assertIn("No source-backed performance table", str(raised.exception))
        self.assertEqual(raised.exception.gap, f"Source data required: {required_source}")

    def test_assumption_model_rejects_inputs_outside_declared_domain(self) -> None:
        model = self.make_model(maximum_bank_rad=math.radians(20.0))
        with self.assertRaisesRegex(UnsupportedModelError, "Bank.*outside"):
            self.simulate(
                aircraft_model=model,
                flight_input=self.make_input(bank_rad=math.radians(30.0)),
                termination=ElapsedTime(1.0),
            )


if __name__ == "__main__":
    unittest.main()
