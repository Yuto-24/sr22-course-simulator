"""Domain errors raised instead of manufacturing unsupported model output."""

from __future__ import annotations


class SimulatorError(Exception):
    """Base class for simulator-domain failures."""


class ValidationError(SimulatorError, ValueError):
    """A domain object or configuration is internally invalid."""


class UnsupportedModelError(SimulatorError):
    """The requested response is outside documented model coverage."""

    def __init__(self, message: str, *, gap: str | None = None) -> None:
        """
        Initialize an unsupported-model error with a description of the coverage gap.
        
        Parameters:
            message (str): Description of the unsupported model or response.
            gap (str | None): Optional description of the specific coverage gap; defaults to
                the error message.
        """
        super().__init__(message)
        self.gap = gap or message


class SimulationLimitError(SimulatorError):
    """Integration reached its safety bound without a termination event."""
