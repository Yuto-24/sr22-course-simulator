"""Access to the small, verified canonical POH slice bundled with the package."""

from __future__ import annotations

from importlib.resources import as_file, files

from sr22_course_simulator.performance.loader import load_performance_table
from sr22_course_simulator.performance.table import RectilinearPerformanceTable

_CANONICAL_PACKAGE = "sr22_course_simulator.data.poh.canonical"


def load_bundled_poh_table(filename: str) -> RectilinearPerformanceTable:
    """
    Load a bundled canonical performance table from a JSON filename.
    
    Parameters:
        filename (str): Simple `.json` basename of the bundled table.
    
    Returns:
        RectilinearPerformanceTable: The loaded performance table.
    
    Raises:
        ValueError: If `filename` contains a path separator or does not end with `.json`.
        FileNotFoundError: If the named bundled table does not exist.
    """

    if "/" in filename or "\\" in filename or not filename.endswith(".json"):
        raise ValueError("filename must be a simple .json basename")
    resource = files(_CANONICAL_PACKAGE).joinpath(filename)
    if not resource.is_file():
        raise FileNotFoundError(filename)
    with as_file(resource) as path:
        return load_performance_table(path)


def bundled_poh_table_names() -> tuple[str, ...]:
    """List the available bundled POH performance table filenames.
    
    Returns:
    	tuple[str, ...]: Sorted `.json` filenames available in the canonical POH resource package.
    """
    return tuple(
        sorted(item.name for item in files(_CANONICAL_PACKAGE).iterdir() if item.name.endswith(".json"))
    )
