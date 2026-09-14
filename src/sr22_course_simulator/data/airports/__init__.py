"""Canonical airport master data."""

from sr22_course_simulator.data.airports.loader import load_airport
from sr22_course_simulator.data.airports.rjfm import RJFM

__all__ = ["RJFM", "load_airport"]
