"""Runnable Spiral Descent examples using an assumption-dependent local model.

This module is not a source-backed SR22 performance prediction.  It demonstrates
the simulation/guidance architecture until the missing descent response is
calibrated or supported by an applicable source.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

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
)
from sr22_course_simulator.environment import Atmosphere, ConstantWind, Environment, FlatTerrain, NoWind
from sr22_course_simulator.export import trajectory_to_kml, write_kml
from sr22_course_simulator.geometry import displace_position
from sr22_course_simulator.guidance import SpiralGuidanceConfig, simulate_guided_spiral_descent
from sr22_course_simulator.maneuver import spiral_descent_package
from sr22_course_simulator.path import PylonSpiralPath
from sr22_course_simulator.simulation import (
    AccumulatedTurn,
    ConstantFlightInput,
    ElapsedTime,
    SimulationConfig,
    coordinated_turn_radius_m,
    simulate_forward,
)
from sr22_course_simulator.units import degrees_to_radians, feet_to_metres, knots_to_metres_per_second


def build_assumption_model() -> QuasiSteadyAircraftModel:
    """Build conspicuously synthetic local closure parameters for the demo."""

    domain = AssumptionDomain(
        minimum_pitch_rad=degrees_to_radians(-10.0),
        maximum_pitch_rad=degrees_to_radians(10.0),
        minimum_bank_rad=degrees_to_radians(-60.0),
        maximum_bank_rad=degrees_to_radians(60.0),
        minimum_power_fraction=0.0,
        maximum_power_fraction=0.4,
        supported_flaps=(FlapSetting.RETRACTED,),
    )
    performance = AssumedSteadyPointProvider(
        domain=domain,
        reference_true_airspeed_mps=knots_to_metres_per_second(110.0),
        reference_power_fraction=0.15,
        reference_pitch_rad=degrees_to_radians(-1.0),
        tas_per_power_fraction_mps=8.0,
        tas_per_pitch_rad_mps=8.0,
        zero_power_fuel_flow_kg_s=0.0002,
        fuel_flow_per_power_fraction_kg_s=0.02,
    )
    return QuasiSteadyAircraftModel(
        name="DEMO ONLY — assumption-dependent local steady point",
        performance=performance,
        longitudinal_closure=AssumedAngleOfAttackClosure(degrees_to_radians(2.0)),
    )


def build_initial_state() -> InitialState:
    return InitialState(
        time_s=0.0,
        position=GeoPosition(34.7500, 135.4500),
        altitude_m=feet_to_metres(4_000.0),
        heading_true_rad=degrees_to_radians(90.0),
        true_airspeed_mps=knots_to_metres_per_second(110.0),
        loading=Loading(
            empty_aircraft_mass_kg=1_050.0,
            payload=(MassItem("synthetic demo payload", 180.0),),
        ),
        initial_fuel_mass_kg=90.0,
    )


def run_forward_demo(*, wind: bool = False):
    initial = build_initial_state()
    environment = Environment(
        atmosphere=Atmosphere(temperature_k=288.15, pressure_altitude_m=initial.altitude_m),
        wind=ConstantWind.from_meteorological_knots(from_direction_deg_true=270.0, speed_kt=10.0)
        if wind
        else NoWind(),
        terrain=FlatTerrain(0.0),
    )
    return simulate_forward(
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
        aircraft_model=build_assumption_model(),
        termination=ElapsedTime(60.0),
        config=SimulationConfig(dt_s=0.2, max_steps=1_000),
    )


def run_guided_demo(*, wind: bool = True):
    initial = build_initial_state()
    model = build_assumption_model()
    target_tas = knots_to_metres_per_second(110.0)
    radius = abs(coordinated_turn_radius_m(target_tas, degrees_to_radians(45.0)))
    center = displace_position(initial.position, east_m=0.0, north_m=-radius)
    path = PylonSpiralPath(
        name="Assumed two-turn pylon Reference Path",
        center=center,
        radius_m=radius,
        start_bearing_rad=0.0,
        sweep_rad=2.0 * math.tau,
        start_altitude_m=initial.altitude_m,
        end_altitude_m=initial.altitude_m - feet_to_metres(700.0),
        point_count=361,
    )
    environment = Environment(
        atmosphere=Atmosphere(temperature_k=288.15, pressure_altitude_m=initial.altitude_m),
        wind=ConstantWind.from_meteorological_knots(from_direction_deg_true=270.0, speed_kt=10.0)
        if wind
        else NoWind(),
        terrain=FlatTerrain(0.0),
    )
    guidance_config = SpiralGuidanceConfig(
        interpret_unspecified_airspeed_as_tas=True,
        entry_duration_s=8.0,
        established_power_fraction=0.15,
        trim_pitch_rad=degrees_to_radians(-1.0),
        speed_error_to_pitch_gain_rad_per_mps=degrees_to_radians(0.12),
        heading_error_to_bank_gain=0.7,
        radial_error_gain_per_m=0.002,
        maximum_intercept_angle_rad=degrees_to_radians(25.0),
        flap=FlapSetting.RETRACTED,
    )
    package = spiral_descent_package()
    return simulate_guided_spiral_descent(
        initial=initial,
        environment=environment,
        maneuver_spec=package.spec,
        reference_path=path,
        guidance_config=guidance_config,
        aircraft_model=model,
        termination=AccumulatedTurn(2.0 * math.tau),
        simulation_config=SimulationConfig(dt_s=0.2, max_steps=2_000),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("forward", "guided"), default="guided")
    parser.add_argument("--calm", action="store_true", help="use NoWind")
    parser.add_argument("--kml", type=Path, help="write trajectory KML")
    parser.add_argument("--plot", action="store_true", help="show optional Matplotlib plots")
    args = parser.parse_args()

    if args.mode == "forward":
        result = run_forward_demo(wind=not args.calm)
        simulation = result
        reference_path = None
    else:
        guided = run_guided_demo(wind=not args.calm)
        simulation = guided.simulation
        reference_path = guided.reference_path

    print("WARNING: DEMO ONLY — output uses an assumption-dependent response model, not POH descent data.")
    print(
        f"mode={simulation.mode} outcome={simulation.outcome.value} "
        f"samples={len(simulation.trajectory)} final_altitude_m={simulation.trajectory.final.altitude_m:.1f}"
    )
    if args.kml:
        write_kml(trajectory_to_kml(simulation.trajectory, name=f"Spiral Descent {args.mode}"), args.kml)
        print(f"wrote {args.kml}")
    if args.plot:
        from matplotlib import pyplot as plt

        from sr22_course_simulator.plotting import (
            plot_altitude_time,
            plot_ground_track,
            plot_trajectory_3d,
        )

        plot_ground_track(simulation.trajectory, reference_path=reference_path)
        plot_altitude_time(simulation.trajectory)
        plot_trajectory_3d(simulation.trajectory, reference_path=reference_path)
        plt.show()


if __name__ == "__main__":
    main()
