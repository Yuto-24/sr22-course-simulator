from __future__ import annotations

import math
import tempfile
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

from sr22_course_simulator.aircraft import AircraftState, FlapSetting, GeoPosition
from sr22_course_simulator.environment import ConstantWind, NoWind
from sr22_course_simulator.export import reference_path_to_kml, trajectory_to_kml, write_kml
from sr22_course_simulator.geometry import distance_m, displace_position
from sr22_course_simulator.path import PathPoint, PolylineReferencePath, PylonSpiralPath
from sr22_course_simulator.simulation import Trajectory


def _state(time_s: float, position: GeoPosition, altitude_m: float) -> AircraftState:
    return AircraftState(
        time_s=time_s,
        position=position,
        altitude_m=altitude_m,
        heading_true_rad=0.0,
        track_true_rad=0.0,
        true_airspeed_mps=50.0,
        ground_speed_mps=50.0,
        vertical_speed_mps=-2.0,
        pitch_rad=-0.02,
        bank_rad=0.2,
        power_fraction=0.2,
        flap=FlapSetting.RETRACTED,
        fuel_remaining_kg=80.0,
        fuel_burned_kg=time_s * 0.01,
        weight_kg=1_300.0 - time_s * 0.01,
        accumulated_turn_rad=0.1 * time_s,
    )


def _coordinates(kml: str) -> list[tuple[float, float, float]]:
    root = ET.fromstring(kml)
    namespace = {"k": "http://www.opengis.net/kml/2.2"}
    text = root.findtext(".//k:coordinates", namespaces=namespace)
    assert text is not None
    return [tuple(map(float, line.split(","))) for line in text.splitlines()]


class ReferencePathTests(unittest.TestCase):
    def test_pylon_path_radius_sweep_and_altitude_are_geometric(self) -> None:
        center = GeoPosition(35.0, 135.0)
        path = PylonSpiralPath(
            name="two-turn path",
            center=center,
            radius_m=300.0,
            start_bearing_rad=0.0,
            sweep_rad=2.0 * math.tau,
            start_altitude_m=1_500.0,
            end_altitude_m=900.0,
            point_count=9,
        )
        points = path.points()
        self.assertEqual(len(points), 9)
        self.assertAlmostEqual(points[0].altitude_m, 1_500.0)
        self.assertAlmostEqual(points[-1].altitude_m, 900.0)
        for point in points:
            self.assertAlmostEqual(distance_m(center, point.position), 300.0, delta=0.02)
        self.assertLess(distance_m(points[0].position, points[-1].position), 0.02)

    def test_wind_objects_cannot_modify_reference_path(self) -> None:
        center = GeoPosition(35.0, 135.0)
        path = PylonSpiralPath(
            name="wind-independent",
            center=center,
            radius_m=250.0,
            start_bearing_rad=0.3,
            sweep_rad=math.tau,
            start_altitude_m=1_000.0,
            end_altitude_m=800.0,
            point_count=21,
        )
        before = path.points()
        # Exercise both providers; neither is accepted by or stored on the path.
        NoWind().velocity_at(center, 1_000.0, 0.0)
        ConstantWind.from_meteorological_knots(
            from_direction_deg_true=270.0, speed_kt=25.0
        ).velocity_at(center, 1_000.0, 0.0)
        self.assertEqual(path.points(), before)
        self.assertFalse(hasattr(path, "wind"))

    def test_projection_exposes_radial_error_and_tangent(self) -> None:
        center = GeoPosition(0.0, 0.0)
        path = PylonSpiralPath(
            name="right orbit",
            center=center,
            radius_m=100.0,
            start_bearing_rad=0.0,
            sweep_rad=math.tau,
            start_altitude_m=100.0,
            end_altitude_m=90.0,
        )
        north_120 = displace_position(center, east_m=0.0, north_m=120.0)
        projection = path.project(north_120)
        self.assertAlmostEqual(projection.radial_error_m, 20.0, places=6)
        self.assertAlmostEqual(projection.tangent_track_true_rad, math.pi / 2, places=6)


class KmlTests(unittest.TestCase):
    def test_trajectory_kml_uses_lon_lat_alt_and_preserves_altitude(self) -> None:
        p0 = GeoPosition(35.1, 135.2)
        p1 = GeoPosition(35.1002, 135.2004)
        trajectory = Trajectory((_state(0.0, p0, 1_234.5), _state(1.0, p1, 1_230.25)))
        kml = trajectory_to_kml(trajectory, name="unsafe <name> & escaped")
        coordinates = _coordinates(kml)
        self.assertEqual(coordinates, [(135.2, 35.1, 1_234.5), (135.2004, 35.1002, 1_230.25)])
        root = ET.fromstring(kml)
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        self.assertEqual(root.findtext(".//k:altitudeMode", namespaces=ns), "absolute")
        self.assertEqual(root.findtext(".//k:Placemark/k:name", namespaces=ns), "unsafe <name> & escaped")

    def test_reference_path_kml_uses_same_infrastructure(self) -> None:
        path = PolylineReferencePath(
            "reference",
            (
                PathPoint(GeoPosition(34.0, 133.0), 300.0),
                PathPoint(GeoPosition(34.1, 133.2), 250.0),
                PathPoint(GeoPosition(34.2, 133.4), 200.0),
            ),
        )
        self.assertEqual(
            _coordinates(reference_path_to_kml(path)),
            [(133.0, 34.0, 300.0), (133.2, 34.1, 250.0), (133.4, 34.2, 200.0)],
        )

    def test_kml_coordinate_count_and_file_write(self) -> None:
        trajectory = Trajectory(
            (
                _state(0.0, GeoPosition(1.0, 2.0), 3.0),
                _state(1.0, GeoPosition(1.1, 2.1), 4.0),
                _state(2.0, GeoPosition(1.2, 2.2), 5.0),
            )
        )
        content = trajectory_to_kml(trajectory)
        self.assertEqual(len(_coordinates(content)), 3)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "nested" / "trajectory.kml"
            returned = write_kml(content, destination)
            self.assertEqual(returned, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
