"""KMZ packaging helpers for Google Earth KML documents."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def write_kmz(kml: str, destination: str | Path) -> Path:
    """Write a Google Earth KMZ containing the supplied KML as ``doc.kml``.

    Google Earth discovers the root document at this conventional member name.
    The KML remains the source of geometry, styles, coordinates, and metadata;
    this helper only packages it without altering those semantics.
    """

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", kml.encode("utf-8"))
    return path
