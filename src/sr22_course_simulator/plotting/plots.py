"""Optional Matplotlib views of typed trajectory/path objects."""

from __future__ import annotations

from typing import Any

from sr22_course_simulator.path.reference import ReferencePath
from sr22_course_simulator.simulation.trajectory import Trajectory
from sr22_course_simulator.units import metres_to_feet


def _pyplot():
    try:
        from matplotlib import pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise ImportError(
            "Plotting requires the optional dependency: pip install 'sr22-course-simulator[plot]'"
        ) from exc
    return plt


def plot_ground_track(
    trajectory: Trajectory,
    *,
    reference_path: ReferencePath | None = None,
) -> tuple[Any, Any]:
    """Plot 2D longitude/latitude ground tracks with optional path overlay."""

    plt = _pyplot()
    figure, axes = plt.subplots()
    axes.plot(trajectory.longitudes_deg, trajectory.latitudes_deg, label="Trajectory")
    if reference_path is not None:
        points = reference_path.points()
        axes.plot(
            [point.position.longitude_deg for point in points],
            [point.position.latitude_deg for point in points],
            linestyle="--",
            label="Reference Path",
        )
    axes.set_xlabel("Longitude [deg]")
    axes.set_ylabel("Latitude [deg]")
    axes.set_aspect("equal", adjustable="datalim")
    axes.grid(True)
    axes.legend()
    return figure, axes


def plot_altitude_time(trajectory: Trajectory) -> tuple[Any, Any]:
    plt = _pyplot()
    figure, axes = plt.subplots()
    elapsed = [time - trajectory.initial.time_s for time in trajectory.times_s]
    axes.plot(elapsed, [metres_to_feet(value) for value in trajectory.altitudes_m])
    axes.set_xlabel("Elapsed time [s]")
    axes.set_ylabel("Altitude MSL [ft]")
    axes.grid(True)
    return figure, axes


def plot_trajectory_3d(
    trajectory: Trajectory,
    *,
    reference_path: ReferencePath | None = None,
) -> tuple[Any, Any]:
    plt = _pyplot()
    figure = plt.figure()
    axes = figure.add_subplot(111, projection="3d")
    axes.plot(
        trajectory.longitudes_deg,
        trajectory.latitudes_deg,
        [metres_to_feet(value) for value in trajectory.altitudes_m],
        label="Trajectory",
    )
    if reference_path is not None:
        points = reference_path.points()
        axes.plot(
            [point.position.longitude_deg for point in points],
            [point.position.latitude_deg for point in points],
            [metres_to_feet(point.altitude_m) for point in points],
            linestyle="--",
            label="Reference Path",
        )
    axes.set_xlabel("Longitude [deg]")
    axes.set_ylabel("Latitude [deg]")
    axes.set_zlabel("Altitude MSL [ft]")
    axes.legend()
    return figure, axes
