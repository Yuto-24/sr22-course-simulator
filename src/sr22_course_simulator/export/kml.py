"""KML 2.2 export for trajectories and wind-independent reference paths."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from sr22_course_simulator.path.reference import ReferencePath
from sr22_course_simulator.simulation.trajectory import Trajectory

KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NAMESPACE)


def _tag(name: str) -> str:
    return f"{{{KML_NAMESPACE}}}{name}"


def _coordinate_text(coordinates: tuple[tuple[float, float, float], ...]) -> str:
    return "\n".join(f"{lon:.12g},{lat:.12g},{alt:.12g}" for lon, lat, alt in coordinates)


def _document(name: str, coordinates: tuple[tuple[float, float, float], ...]) -> str:
    if len(coordinates) < 2:
        raise ValueError("KML LineString requires at least two coordinates")
    root = ET.Element(_tag("kml"))
    document = ET.SubElement(root, _tag("Document"))
    ET.SubElement(document, _tag("name")).text = name
    placemark = ET.SubElement(document, _tag("Placemark"))
    ET.SubElement(placemark, _tag("name")).text = name
    line = ET.SubElement(placemark, _tag("LineString"))
    ET.SubElement(line, _tag("tessellate")).text = "0"
    ET.SubElement(line, _tag("altitudeMode")).text = "absolute"
    ET.SubElement(line, _tag("coordinates")).text = _coordinate_text(coordinates)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def trajectory_to_kml(trajectory: Trajectory, *, name: str = "Trajectory") -> str:
    coordinates = tuple(
        (
            state.position.longitude_deg,
            state.position.latitude_deg,
            state.altitude_m,
        )
        for state in trajectory.states
    )
    return _document(name, coordinates)


def reference_path_to_kml(reference_path: ReferencePath, *, name: str | None = None) -> str:
    coordinates = tuple(
        (point.position.longitude_deg, point.position.latitude_deg, point.altitude_m)
        for point in reference_path.points()
    )
    return _document(name or reference_path.name, coordinates)


def write_kml(content: str, destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
