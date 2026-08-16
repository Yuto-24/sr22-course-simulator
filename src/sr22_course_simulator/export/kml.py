"""KML 2.2 export for trajectories and wind-independent reference paths."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree as ET

from sr22_course_simulator.path.reference import ReferencePath
from sr22_course_simulator.simulation.trajectory import Trajectory

KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NAMESPACE)


def _tag(name: str) -> str:
    """Build a namespace-qualified KML element name."""
    return f"{{{KML_NAMESPACE}}}{name}"


def _coordinate_text(coordinates: tuple[tuple[float, float, float], ...]) -> str:
    """Format coordinate triples as newline-separated KML coordinate text."""
    return "\n".join(f"{lon:.12g},{lat:.12g},{alt:.12g}" for lon, lat, alt in coordinates)


def _append_line_placemark(
    document: ET.Element,
    *,
    name: str,
    coordinates: tuple[tuple[float, float, float], ...],
) -> None:
    """Append one absolute-altitude LineString placemark."""

    if len(coordinates) < 2:
        raise ValueError("KML LineString requires at least two coordinates")
    placemark = ET.SubElement(document, _tag("Placemark"))
    ET.SubElement(placemark, _tag("name")).text = name
    line = ET.SubElement(placemark, _tag("LineString"))
    ET.SubElement(line, _tag("tessellate")).text = "0"
    ET.SubElement(line, _tag("altitudeMode")).text = "absolute"
    ET.SubElement(line, _tag("coordinates")).text = _coordinate_text(coordinates)


def _document(
    name: str,
    placemarks: tuple[
        tuple[str, tuple[tuple[float, float, float], ...]],
        ...,
    ],
) -> str:
    """Create a KML document containing one or more LineStrings."""

    if not placemarks:
        raise ValueError("KML Document requires at least one placemark")
    root = ET.Element(_tag("kml"))
    document = ET.SubElement(root, _tag("Document"))
    ET.SubElement(document, _tag("name")).text = name
    for placemark_name, coordinates in placemarks:
        _append_line_placemark(
            document,
            name=placemark_name,
            coordinates=coordinates,
        )
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def trajectory_to_kml(trajectory: Trajectory, *, name: str = "Trajectory") -> str:
    """
    Convert trajectory states to a KML document.
    
    Parameters:
        name (str): Name assigned to the KML placemark.
    
    Returns:
        str: KML document containing the trajectory coordinates.
    
    Raises:
        ValueError: If the trajectory contains fewer than two states.
    """
    coordinates = tuple(
        (
            state.position.longitude_deg,
            state.position.latitude_deg,
            state.altitude_m,
        )
        for state in trajectory.states
    )
    return _document(name, ((name, coordinates),))


def reference_path_to_kml(reference_path: ReferencePath, *, name: str | None = None) -> str:
    """
    Convert a reference path to a KML document containing its coordinates.
    
    Parameters:
    	reference_path (ReferencePath): Reference path whose points are exported.
    	name (str | None): Optional name for the KML placemark. Uses the reference path's name when omitted.
    
    Returns:
    	str: KML document containing the reference path.
    """
    coordinates = tuple(
        (point.position.longitude_deg, point.position.latitude_deg, point.altitude_m)
        for point in reference_path.points()
    )
    placemark_name = name or reference_path.name
    return _document(placemark_name, ((placemark_name, coordinates),))


def reference_paths_to_kml(
    reference_paths: Iterable[ReferencePath],
    *,
    name: str = "Reference Paths",
) -> str:
    """Convert multiple reference paths to one multi-Placemark KML document."""

    paths = tuple(reference_paths)
    placemarks = tuple(
        (
            path.name,
            tuple(
                (
                    point.position.longitude_deg,
                    point.position.latitude_deg,
                    point.altitude_m,
                )
                for point in path.points()
            ),
        )
        for path in paths
    )
    return _document(name, placemarks)


def write_kml(content: str, destination: str | Path) -> Path:
    """
    Write KML content to a file, creating its parent directories as needed.
    
    Parameters:
    	content (str): KML content to write.
    	destination (str | Path): Destination file path.
    
    Returns:
    	Path: The path of the written file.
    """
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
