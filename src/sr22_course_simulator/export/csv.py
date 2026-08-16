"""CSV export for time-indexed trajectory states."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from sr22_course_simulator.simulation.trajectory import Trajectory
from sr22_course_simulator.units import (
    metres_per_second_to_feet_per_minute,
    metres_per_second_to_knots,
    metres_to_feet,
    radians_to_degrees,
)


TRAJECTORY_CSV_FIELDS = (
    "time_s",
    "latitude_deg",
    "longitude_deg",
    "altitude_m",
    "altitude_ft",
    "heading_true_deg",
    "track_true_deg",
    "true_airspeed_mps",
    "true_airspeed_kt",
    "ground_speed_mps",
    "ground_speed_kt",
    "vertical_speed_mps",
    "vertical_speed_fpm",
    "pitch_deg",
    "bank_deg",
    "power_pct",
    "flap",
    "fuel_remaining_kg",
    "fuel_burned_kg",
    "weight_kg",
    "accumulated_turn_deg",
    "evidence",
)


def trajectory_to_csv(trajectory: Trajectory) -> str:
    """Serialize all trajectory states to CSV with values expressed in the units specified by the column names.
    
    Parameters:
    	trajectory (Trajectory): Trajectory whose states are serialized.
    
    Returns:
    	str: CSV text containing a header and one row for each trajectory state.
    """

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=TRAJECTORY_CSV_FIELDS)
    writer.writeheader()
    for state in trajectory.states:
        writer.writerow(
            {
                "time_s": state.time_s,
                "latitude_deg": state.position.latitude_deg,
                "longitude_deg": state.position.longitude_deg,
                "altitude_m": state.altitude_m,
                "altitude_ft": metres_to_feet(state.altitude_m),
                "heading_true_deg": state.heading_true_deg,
                "track_true_deg": state.track_true_deg,
                "true_airspeed_mps": state.true_airspeed_mps,
                "true_airspeed_kt": metres_per_second_to_knots(state.true_airspeed_mps),
                "ground_speed_mps": state.ground_speed_mps,
                "ground_speed_kt": metres_per_second_to_knots(state.ground_speed_mps),
                "vertical_speed_mps": state.vertical_speed_mps,
                "vertical_speed_fpm": metres_per_second_to_feet_per_minute(
                    state.vertical_speed_mps
                ),
                "pitch_deg": radians_to_degrees(state.pitch_rad),
                "bank_deg": radians_to_degrees(state.bank_rad),
                "power_pct": state.power_fraction * 100.0,
                "flap": state.flap.value,
                "fuel_remaining_kg": state.fuel_remaining_kg,
                "fuel_burned_kg": state.fuel_burned_kg,
                "weight_kg": state.weight_kg,
                "accumulated_turn_deg": radians_to_degrees(state.accumulated_turn_rad),
                "evidence": ";".join(item.value for item in state.evidence),
            }
        )
    return stream.getvalue()


def write_trajectory_csv(trajectory: Trajectory, destination: str | Path) -> Path:
    """Write a trajectory CSV file, creating parent directories when needed."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trajectory_to_csv(trajectory), encoding="utf-8", newline="")
    return path
