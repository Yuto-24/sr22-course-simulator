"""Optional Matplotlib views of typed trajectory/path objects."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from sr22_course_simulator.path.reference import ReferencePath
from sr22_course_simulator.simulation.trajectory import Trajectory
from sr22_course_simulator.units import metres_to_feet


def _pyplot():
    """
    Load and return Matplotlib's pyplot module.
    
    Returns:
        module: The imported Matplotlib pyplot module.
    
    Raises:
        ImportError: If Matplotlib is unavailable.
    """
    try:
        from matplotlib import pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise ImportError(
            "Plotting requires the optional dependency: pip install 'sr22-course-simulator[plot]'"
        ) from exc
    return plt


def _longitude_latitude_aspect(latitudes_deg: Iterable[float]) -> float | str:
    """
    Determine the display aspect ratio for longitude and latitude coordinates.
    
    Parameters:
        latitudes_deg (Iterable[float]): Latitude values in degrees used to estimate the representative latitude.
    
    Returns:
        float | str: The longitude-to-latitude aspect ratio, or ``"auto"`` for empty input or latitudes near the poles.
    """

    latitudes = tuple(float(value) for value in latitudes_deg)
    if not latitudes:
        return "auto"
    representative_latitude = 0.5 * (min(latitudes) + max(latitudes))
    longitude_scale = abs(math.cos(math.radians(representative_latitude)))
    if longitude_scale <= 1e-12:
        return "auto"
    return 1.0 / longitude_scale


def plot_ground_track(
    trajectory: Trajectory,
    *,
    reference_path: ReferencePath | None = None,
) -> tuple[Any, Any]:
    """
    Plot the trajectory's longitude and latitude, optionally overlaying a reference path.
    
    Parameters:
        trajectory (Trajectory): Trajectory whose ground track is plotted.
        reference_path (ReferencePath | None): Optional path to overlay for comparison.
    
    Returns:
        tuple[Any, Any]: The Matplotlib figure and axes containing the plot.
    """

    plt = _pyplot()
    figure, axes = plt.subplots()
    axes.plot(trajectory.longitudes_deg, trajectory.latitudes_deg, label="Trajectory")
    path_points = ()
    if reference_path is not None:
        path_points = reference_path.points()
        axes.plot(
            [point.position.longitude_deg for point in path_points],
            [point.position.latitude_deg for point in path_points],
            linestyle="--",
            label="Reference Path",
        )
    axes.set_xlabel("Longitude [deg]")
    axes.set_ylabel("Latitude [deg]")
    axes.set_aspect(
        _longitude_latitude_aspect(
            (
                *trajectory.latitudes_deg,
                *(point.position.latitude_deg for point in path_points),
            )
        ),
        adjustable="datalim",
    )
    axes.grid(True)
    axes.legend()
    return figure, axes


def plot_altitude_time(trajectory: Trajectory) -> tuple[Any, Any]:
    """Plot mean sea level altitude against elapsed time since the trajectory start.
    
    Parameters:
    	trajectory (Trajectory): Trajectory containing timestamps and altitudes.
    
    Returns:
    	tuple[Any, Any]: The Matplotlib figure and axes containing the plot.
    """
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
    """
    Create a 3D longitude, latitude, and altitude plot for a trajectory.
    
    Parameters:
    	reference_path (ReferencePath | None): Optional path to overlay on the plot.
    
    Returns:
    	tuple[Any, Any]: The Matplotlib figure and 3D axes.
    """
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
