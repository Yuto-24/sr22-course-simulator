from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError, replace

from sr22_course_simulator.aircraft import (
    AirspeedKind,
    AircraftState,
    FlapSetting,
    FlightInput,
    GeoPosition,
    InitialState,
    Loading,
    MassItem,
    QuasiSteadyResponse,
)
from sr22_course_simulator.environment import (
    Atmosphere,
    ConstantWind,
    Environment,
    FlatTerrain,
    NoWind,
)
from sr22_course_simulator.errors import UnsupportedModelError
from sr22_course_simulator.geometry import displace_position
from sr22_course_simulator.guidance import (
    SpiralDescentGuidance,
    SpiralGuidanceConfig,
    simulate_guided_spiral_descent,
)
from sr22_course_simulator.maneuver import AdvisoryValue, ControlChannel, spiral_descent_package
from sr22_course_simulator.path import PylonSpiralPath
from sr22_course_simulator.provenance import EvidenceKind
from sr22_course_simulator.simulation import (
    ConstantFlightInput,
    ElapsedTime,
    SimulationConfig,
    SimulationProgress,
    simulate_forward,
)
from sr22_course_simulator.units import degrees_to_radians, knots_to_metres_per_second


def _only_quantity(items, quantity: str):
    matches = [item for item in items if item.quantity == quantity]
    if len(matches) != 1:
        raise AssertionError(f"expected one {quantity!r}, found {len(matches)}")
    return matches[0]


def _control_for(items, controlled_quantity: str):
    matches = [item for item in items if item.controlled_quantity == controlled_quantity]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one control relationship for {controlled_quantity!r}, found {len(matches)}"
        )
    return matches[0]


class SpiralDescentSourceSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = spiral_descent_package()
        self.spec = self.package.spec

    def test_entry_airspeed_and_power_have_distinct_semantic_roles(self) -> None:
        entry = self.spec.phase("entry")
        airspeed = _only_quantity(entry.targets, "airspeed_at_pylon_abeam")
        power = _only_quantity(entry.initial_settings, "power")

        self.assertEqual((airspeed.value, airspeed.unit), (110.0, "kt"))
        self.assertIs(airspeed.airspeed_kind, AirspeedKind.UNSPECIFIED)
        self.assertIs(airspeed.evidence, EvidenceKind.PROCEDURE_TARGET)

        self.assertEqual((power.value, power.unit), (10.0, "percent"))
        self.assertTrue(power.approximate)
        self.assertIs(power.evidence, EvidenceKind.PROCEDURE_INITIAL_SETTING)
        self.assertFalse(any(item.quantity == "power" for item in entry.targets))

    def test_execution_pitch_bank_and_control_relationships_are_separate(self) -> None:
        execution = self.spec.phase("execution")
        airspeed = _only_quantity(execution.targets, "airspeed")
        pitch = _only_quantity(execution.initial_settings, "pitch")
        bank = _only_quantity(execution.nominals, "bank")
        maximum_bank = _only_quantity(execution.limits, "absolute_bank")

        self.assertEqual((airspeed.value, airspeed.unit), (110.0, "kt"))
        self.assertIs(airspeed.airspeed_kind, AirspeedKind.UNSPECIFIED)

        self.assertEqual((pitch.value, pitch.unit), (-1.0, "deg"))
        self.assertTrue(pitch.approximate)
        self.assertFalse(any(item.quantity == "pitch" for item in execution.targets))
        self.assertFalse(any(item.quantity == "pitch" for item in execution.nominals))

        self.assertEqual((bank.value, bank.unit), (45.0, "deg"))
        self.assertTrue(bank.adjustable)
        self.assertEqual((maximum_bank.value, maximum_bank.unit), (55.0, "deg"))
        self.assertEqual(maximum_bank.direction.value, "maximum")

        speed_control = _control_for(execution.control_relationships, "target airspeed")
        path_control = _control_for(
            execution.control_relationships,
            "pylon / desired ground-path relationship",
        )
        self.assertIs(speed_control.control_input, ControlChannel.PITCH)
        self.assertIn("110", f"{airspeed.value:g}")
        self.assertIs(path_control.control_input, ControlChannel.BANK)
        self.assertIn("pylon", path_control.controlled_quantity.lower())
        self.assertEqual(execution.path_constraints[0].name, "pylon_relationship")

    def test_termination_minimum_height_and_recovery_power(self) -> None:
        completion = _only_quantity(self.spec.termination_conditions, "accumulated_turn")
        minimum_height = _only_quantity(self.spec.safety_constraints, "minimum_training_height")
        recovery_power = _only_quantity(
            self.spec.phase("recovery").initial_settings,
            "power",
        )

        self.assertEqual((completion.value, completion.unit), (720.0, "deg"))
        self.assertTrue(completion.source_defined)
        self.assertEqual(
            (minimum_height.value, minimum_height.unit, minimum_height.reference),
            (2000.0, "ft", "AGL"),
        )
        self.assertEqual((recovery_power.value, recovery_power.unit), (100.0, "percent"))
        self.assertFalse(recovery_power.approximate)
        self.assertTrue(any("MAX Power" in note for note in recovery_power.notes))

    def test_exact_reference_data_row_is_separate_and_advisory(self) -> None:
        self.assertEqual(len(self.package.advisory_references), 1)
        advisory = self.package.advisory_references[0]
        actual = tuple((item.quantity, item.value, item.unit) for item in advisory.values)

        self.assertEqual(
            actual,
            (
                ("airspeed", 110.0, "kt"),
                ("pitch", -1.0, "deg"),
                ("power", 10.0, "percent"),
                ("bank", 45.0, "deg"),
                ("gear", "DOWN", None),
                ("flaps", "UP", None),
            ),
        )
        self.assertIs(advisory.evidence, EvidenceKind.ADVISORY_REFERENCE)
        self.assertFalse(hasattr(self.spec, "advisory_references"))

    def test_primary_pdf_page_citations_are_retained(self) -> None:
        self.assertEqual(
            self.spec.source.page,
            "5-(34) to 5-(35) (PDF pages 157-158)",
        )
        self.assertIn("157", self.spec.source.page)
        self.assertIn("158", self.spec.source.page)
        self.assertEqual(
            self.package.advisory_references[0].citation.page,
            "5-(49) (PDF page 172)",
        )
        minimum_height = _only_quantity(self.spec.safety_constraints, "minimum_training_height")
        self.assertEqual(minimum_height.citation.page, "5-(1) (PDF page 124)")

        narrative_items = (
            _only_quantity(self.spec.phase("entry").targets, "airspeed_at_pylon_abeam"),
            _only_quantity(self.spec.phase("entry").initial_settings, "power"),
            _only_quantity(self.spec.phase("execution").initial_settings, "pitch"),
            _only_quantity(self.spec.phase("execution").nominals, "bank"),
            _only_quantity(self.spec.phase("execution").limits, "absolute_bank"),
            _only_quantity(self.spec.phase("recovery").initial_settings, "power"),
        )
        self.assertTrue(all(item.citation == self.spec.source for item in narrative_items))


class _ConstantAssumptionResponseModel:
    name = "synthetic test response — not SR22 performance"

    def resolve(self, state, flight_input, environment) -> QuasiSteadyResponse:
        return QuasiSteadyResponse(
            true_airspeed_mps=knots_to_metres_per_second(110.0),
            flight_path_angle_rad=degrees_to_radians(-2.0),
            fuel_flow_kg_s=0.001,
            evidence=(EvidenceKind.ASSUMED,),
            notes=("Synthetic test response only.",),
        )


class SpiralGuidanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = spiral_descent_package()
        self.center = GeoPosition(34.75, 135.45)
        self.radius_m = 700.0
        self.path = PylonSpiralPath(
            name="test two-turn pylon path",
            center=self.center,
            radius_m=self.radius_m,
            start_bearing_rad=0.0,
            sweep_rad=2.0 * math.tau,
            start_altitude_m=1200.0,
            end_altitude_m=900.0,
            point_count=73,
        )
        self.loading = Loading(
            empty_aircraft_mass_kg=1050.0,
            payload=(MassItem("test payload", 150.0),),
        )
        self.target_tas_mps = knots_to_metres_per_second(110.0)
        self.config = SpiralGuidanceConfig(
            interpret_unspecified_airspeed_as_tas=True,
            entry_duration_s=5.0,
            established_power_fraction=0.23,
            trim_pitch_rad=degrees_to_radians(-2.5),
            speed_error_to_pitch_gain_rad_per_mps=degrees_to_radians(0.2),
            heading_error_to_bank_gain=0.8,
            radial_error_gain_per_m=0.001,
            maximum_intercept_angle_rad=degrees_to_radians(25.0),
            flap=FlapSetting.RETRACTED,
        )

    def environment(self, wind=None) -> Environment:
        return Environment(
            atmosphere=Atmosphere(temperature_k=288.15, pressure_altitude_m=1200.0),
            wind=wind or NoWind(),
            terrain=FlatTerrain(0.0),
        )

    def initial_state(
        self,
        *,
        position: GeoPosition | None = None,
        heading_true_rad: float = math.pi / 2.0,
        true_airspeed_mps: float | None = None,
    ) -> InitialState:
        return InitialState(
            time_s=0.0,
            position=position or self.path.points()[0].position,
            altitude_m=1200.0,
            heading_true_rad=heading_true_rad,
            true_airspeed_mps=(
                self.target_tas_mps
                if true_airspeed_mps is None
                else true_airspeed_mps
            ),
            loading=self.loading,
            initial_fuel_mass_kg=50.0,
        )

    def aircraft_state(
        self,
        *,
        position: GeoPosition | None = None,
        heading_true_rad: float = math.pi / 2.0,
        true_airspeed_mps: float | None = None,
        time_s: float = 10.0,
    ) -> AircraftState:
        tas = self.target_tas_mps if true_airspeed_mps is None else true_airspeed_mps
        return AircraftState(
            time_s=time_s,
            position=position or self.path.points()[0].position,
            altitude_m=1180.0,
            heading_true_rad=heading_true_rad,
            track_true_rad=heading_true_rad,
            true_airspeed_mps=tas,
            ground_speed_mps=tas,
            vertical_speed_mps=-1.0,
            pitch_rad=0.0,
            bank_rad=0.0,
            power_fraction=0.2,
            flap=FlapSetting.RETRACTED,
            fuel_remaining_kg=49.0,
            fuel_burned_kg=1.0,
            weight_kg=self.loading.gross_mass_kg(49.0),
            accumulated_turn_rad=0.0,
        )

    def guidance(self, config: SpiralGuidanceConfig | None = None) -> SpiralDescentGuidance:
        return SpiralDescentGuidance(
            self.package.spec,
            self.path,
            config or self.config,
        )

    def execution_command(
        self,
        guidance: SpiralDescentGuidance,
        state: AircraftState,
        environment: Environment,
    ) -> FlightInput:
        return guidance.input_at(
            state,
            SimulationProgress(step=20, elapsed_s=10.0, accumulated_turn_rad=0.0),
            environment,
        )

    def test_unspecified_procedure_speed_requires_explicit_tas_interpretation(self) -> None:
        config = replace(self.config, interpret_unspecified_airspeed_as_tas=False)
        guidance = self.guidance(config)

        with self.assertRaisesRegex(UnsupportedModelError, "explicit interpretation"):
            guidance.initial_input(self.initial_state(), self.environment())

    def test_entry_power_does_not_leak_into_execution_phase(self) -> None:
        guidance = self.guidance()
        initial_command = guidance.initial_input(self.initial_state(), self.environment())
        execution_command = self.execution_command(
            guidance,
            self.aircraft_state(),
            self.environment(),
        )

        self.assertAlmostEqual(initial_command.power_fraction, 0.10)
        self.assertAlmostEqual(execution_command.power_fraction, 0.23)
        self.assertNotEqual(initial_command.power_fraction, execution_command.power_fraction)
        self.assertEqual(tuple(item.phase for item in guidance.history), ("entry", "execution"))

    def test_pitch_is_live_airspeed_control_not_fixed_reference_value(self) -> None:
        guidance = self.guidance()
        at_target = self.execution_command(
            guidance,
            self.aircraft_state(true_airspeed_mps=self.target_tas_mps),
            self.environment(),
        )
        faster = self.execution_command(
            guidance,
            self.aircraft_state(true_airspeed_mps=self.target_tas_mps + 5.0),
            self.environment(),
        )

        self.assertAlmostEqual(at_target.pitch_rad, self.config.trim_pitch_rad)
        self.assertNotAlmostEqual(at_target.pitch_rad, degrees_to_radians(-1.0))
        self.assertGreater(faster.pitch_rad, at_target.pitch_rad)

    def test_bank_changes_for_path_and_wind_error_and_clips_at_55_degrees(self) -> None:
        guidance = self.guidance()
        calm = self.environment()
        on_path = self.aircraft_state()
        nominal = self.execution_command(guidance, on_path, calm)

        outside = displace_position(
            self.center,
            east_m=0.0,
            north_m=self.radius_m + 50.0,
        )
        path_corrected = self.execution_command(
            guidance,
            self.aircraft_state(position=outside),
            calm,
        )
        windy = self.environment(
            ConstantWind.from_meteorological_knots(
                from_direction_deg_true=180.0,
                speed_kt=20.0,
            )
        )
        wind_corrected = self.execution_command(guidance, on_path, windy)
        clipped = self.execution_command(
            guidance,
            self.aircraft_state(heading_true_rad=0.0),
            calm,
        )

        self.assertAlmostEqual(nominal.bank_deg, 45.0, places=5)
        self.assertNotAlmostEqual(path_corrected.bank_rad, nominal.bank_rad)
        self.assertNotAlmostEqual(wind_corrected.bank_rad, nominal.bank_rad)
        for command in (nominal, path_corrected, wind_corrected, clipped):
            self.assertLessEqual(abs(command.bank_deg), 55.0 + 1e-10)
        self.assertAlmostEqual(clipped.bank_deg, 55.0, places=10)

    def test_advisory_is_immutable_and_replacement_cannot_change_guidance(self) -> None:
        original = self.package.advisory_references[0]
        with self.assertRaises(FrozenInstanceError):
            original.values[0].value = 999.0  # type: ignore[misc]

        replacement_advisory = replace(
            original,
            values=(
                AdvisoryValue("airspeed", 40.0, "kt"),
                AdvisoryValue("pitch", 20.0, "deg"),
                AdvisoryValue("power", 99.0, "percent"),
                AdvisoryValue("bank", 1.0, "deg"),
                AdvisoryValue("gear", "UP", None),
                AdvisoryValue("flaps", "FULL", None),
            ),
        )
        replaced_package = replace(
            self.package,
            advisory_references=(replacement_advisory,),
        )
        original_guidance = SpiralDescentGuidance(
            self.package.spec,
            self.path,
            self.config,
        )
        replacement_guidance = SpiralDescentGuidance(
            replaced_package.spec,
            self.path,
            self.config,
        )

        original_command = original_guidance.initial_input(
            self.initial_state(),
            self.environment(),
        )
        replacement_command = replacement_guidance.initial_input(
            self.initial_state(),
            self.environment(),
        )
        self.assertIs(replaced_package.spec, self.package.spec)
        self.assertEqual(replacement_command, original_command)
        self.assertEqual(replacement_guidance.history, original_guidance.history)

    def test_reference_path_points_do_not_change_when_guidance_sees_wind(self) -> None:
        before = self.path.points()
        calm_guidance = self.guidance()
        windy_guidance = self.guidance()

        calm_guidance.initial_input(self.initial_state(), self.environment())
        windy_guidance.initial_input(
            self.initial_state(),
            self.environment(
                ConstantWind.from_meteorological_knots(
                    from_direction_deg_true=270.0,
                    speed_kt=25.0,
                )
            ),
        )

        self.assertIs(self.path.points(), before)
        self.assertEqual(self.path.points(), before)

    def test_explicit_guided_run_is_distinct_from_direct_forward_simulation(self) -> None:
        initial = self.initial_state()
        environment = self.environment()
        model = _ConstantAssumptionResponseModel()
        simulation_config = SimulationConfig(dt_s=0.2, max_steps=20)

        guided = simulate_guided_spiral_descent(
            initial=initial,
            environment=environment,
            maneuver_spec=self.package.spec,
            reference_path=self.path,
            guidance_config=self.config,
            aircraft_model=model,
            termination=ElapsedTime(0.6),
            simulation_config=simulation_config,
        )
        forward = simulate_forward(
            initial=initial,
            environment=environment,
            input_source=ConstantFlightInput(
                FlightInput.from_degrees(
                    pitch_deg=-1.0,
                    bank_deg=45.0,
                    power_pct=10.0,
                    flap=FlapSetting.RETRACTED,
                )
            ),
            aircraft_model=model,
            termination=ElapsedTime(0.6),
            config=simulation_config,
        )

        self.assertEqual(guided.simulation.mode, "maneuver_guidance")
        self.assertEqual(forward.mode, "forward")
        self.assertIs(guided.maneuver_spec, self.package.spec)
        self.assertIs(guided.reference_path, self.path)
        self.assertGreater(len(guided.guidance_history), 0)
        self.assertNotEqual(guided.simulation.mode, forward.mode)


if __name__ == "__main__":
    unittest.main()
