"""KML 2.2 export for trajectories and wind-independent reference paths."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from sr22_course_simulator.path.reference import ReferencePath
from sr22_course_simulator.simulation.trajectory import Trajectory

KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NAMESPACE)

_KML_COLOR = re.compile(r"^[0-9a-fA-F]{8}$")


@dataclass(frozen=True, slots=True)
class KmlPathStyle:
    """Optional KML styling for one or more absolute-altitude LineStrings."""

    extrude: bool = False
    line_color: str = "ffffffff"
    line_width: float = 1.0
    fill_color: str = "ffffffff"
    fill: bool = True
    outline: bool = True

    def __post_init__(self) -> None:
        for field_name in ("extrude", "fill", "outline"):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be bool")
        for field_name in ("line_color", "fill_color"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or _KML_COLOR.fullmatch(value) is None:
                raise ValueError(f"{field_name} must be an 8-digit KML color")
            object.__setattr__(self, field_name, value.lower())
        width = float(self.line_width)
        if not math.isfinite(width) or width < 0.0:
            raise ValueError("line_width must be finite and non-negative")
        object.__setattr__(self, "line_width", width)


GOOGLE_EARTH_TRAFFIC_PATTERN_STYLE = KmlPathStyle(
    extrude=True,
    line_color="ffffff00",
    line_width=1.0,
    fill_color="1affffcc",
    fill=True,
    outline=False,
)


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
    style_url: str | None = None,
    extrude: bool = False,
    description: str | None = None,
) -> None:
    """Append one absolute-altitude LineString placemark."""

    if len(coordinates) < 2:
        raise ValueError("KML LineString requires at least two coordinates")
    placemark = ET.SubElement(document, _tag("Placemark"))
    ET.SubElement(placemark, _tag("name")).text = name
    if description is not None:
        ET.SubElement(placemark, _tag("description")).text = description
    if style_url is not None:
        ET.SubElement(placemark, _tag("styleUrl")).text = style_url
    line = ET.SubElement(placemark, _tag("LineString"))
    if extrude:
        ET.SubElement(line, _tag("extrude")).text = "1"
    ET.SubElement(line, _tag("tessellate")).text = "0"
    ET.SubElement(line, _tag("altitudeMode")).text = "absolute"
    ET.SubElement(line, _tag("coordinates")).text = _coordinate_text(coordinates)


def _document(
    name: str,
    placemarks: tuple[
        tuple[str, tuple[tuple[float, float, float], ...]],
        ...,
    ],
    *,
    style: KmlPathStyle | None = None,
    styles: tuple[KmlPathStyle | None, ...] | None = None,
    descriptions: tuple[str | None, ...] | None = None,
) -> str:
    """Create a KML document containing one or more LineStrings."""

    if not placemarks:
        raise ValueError("KML Document requires at least one placemark")
    if style is not None and styles is not None:
        raise ValueError("style and styles are mutually exclusive")
    if styles is not None and len(styles) != len(placemarks):
        raise ValueError("styles must contain one entry per placemark")
    if descriptions is not None and len(descriptions) != len(placemarks):
        raise ValueError("descriptions must contain one entry per placemark")
    root = ET.Element(_tag("kml"))
    document = ET.SubElement(root, _tag("Document"))
    ET.SubElement(document, _tag("name")).text = name
    placemark_styles = styles if styles is not None else (style,) * len(placemarks)
    style_urls: dict[KmlPathStyle, str] = {}
    for placemark_style in placemark_styles:
        if placemark_style is None or placemark_style in style_urls:
            continue
        style_id = (
            "path-style"
            if styles is None
            else f"path-style-{len(style_urls) + 1}"
        )
        style_urls[placemark_style] = f"#{style_id}"
        style_element = ET.SubElement(document, _tag("Style"), {"id": style_id})
        line_style = ET.SubElement(style_element, _tag("LineStyle"))
        ET.SubElement(line_style, _tag("color")).text = placemark_style.line_color
        ET.SubElement(line_style, _tag("width")).text = f"{placemark_style.line_width:g}"
        poly_style = ET.SubElement(style_element, _tag("PolyStyle"))
        ET.SubElement(poly_style, _tag("color")).text = placemark_style.fill_color
        ET.SubElement(poly_style, _tag("fill")).text = "1" if placemark_style.fill else "0"
        ET.SubElement(poly_style, _tag("outline")).text = (
            "1" if placemark_style.outline else "0"
        )
    for (placemark_name, coordinates), placemark_style, description in zip(
        placemarks,
        placemark_styles,
        descriptions if descriptions is not None else (None,) * len(placemarks),
        strict=True,
    ):
        _append_line_placemark(
            document,
            name=placemark_name,
            coordinates=coordinates,
            description=description,
            style_url=(
                style_urls[placemark_style]
                if placemark_style is not None
                else None
            ),
            extrude=placemark_style.extrude if placemark_style is not None else False,
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


def reference_path_to_kml(
    reference_path: ReferencePath,
    *,
    name: str | None = None,
    style: KmlPathStyle | None = None,
) -> str:
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
    return _document(placemark_name, ((placemark_name, coordinates),), style=style)


def reference_paths_to_kml(
    reference_paths: Iterable[ReferencePath],
    *,
    name: str = "Reference Paths",
    style: KmlPathStyle | None = None,
    styles: Iterable[KmlPathStyle | None] | None = None,
    descriptions: Iterable[str | None] | None = None,
) -> str:
    """Convert multiple reference paths to one multi-Placemark KML document.

    ``style`` applies one style to every path. ``styles`` instead supplies one
    style per path, which allows a combined document to retain distinctions
    such as runway-specific colors. ``descriptions`` supplies optional text
    (for example source metadata) per path; XML escaping is automatic.
    """

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
    per_path_styles = tuple(styles) if styles is not None else None
    return _document(
        name,
        placemarks,
        style=style,
        styles=per_path_styles,
        descriptions=tuple(descriptions) if descriptions is not None else None,
    )


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
