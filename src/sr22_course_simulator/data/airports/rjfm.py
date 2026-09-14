"""Miyazaki airport resolved from the canonical AIP source record."""

from sr22_course_simulator.data.airports.loader import load_airport

RJFM = load_airport("RJFM")
RJFM_AD_2_2_SOURCE = RJFM.source
RJFM_AD_2_12_SOURCE = RJFM.runway("09").source
