"""Typed simulation results suitable for plotting, CSV/KML and comparison."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sr22_course_simulator.aircraft.state import AircraftState
from sr22_course_simulator.errors import ValidationError
from sr22_course_simulator.provenance import EvidenceKind, SourceCitation


class SimulationOutcome(str, Enum):
    GOAL_REACHED = "goal_reached"
    SAFETY_STOP = "safety_stop"
    MAX_STEPS = "max_steps"


@dataclass(frozen=True, slots=True)
class Trajectory:
    states: tuple[AircraftState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "states", tuple(self.states))
        if not self.states:
            raise ValidationError("Trajectory must contain at least one state")
        if any(b.time_s <= a.time_s for a, b in zip(self.states, self.states[1:])):
            raise ValidationError("Trajectory state times must be strictly increasing")

    def __len__(self) -> int:
        return len(self.states)

    def __iter__(self):  # type intentionally inferred for a light public API
        return iter(self.states)

    @property
    def initial(self) -> AircraftState:
        return self.states[0]

    @property
    def final(self) -> AircraftState:
        return self.states[-1]

    @property
    def times_s(self) -> tuple[float, ...]:
        return tuple(state.time_s for state in self.states)

    @property
    def latitudes_deg(self) -> tuple[float, ...]:
        return tuple(state.position.latitude_deg for state in self.states)

    @property
    def longitudes_deg(self) -> tuple[float, ...]:
        return tuple(state.position.longitude_deg for state in self.states)

    @property
    def altitudes_m(self) -> tuple[float, ...]:
        return tuple(state.altitude_m for state in self.states)

    @property
    def headings_true_rad(self) -> tuple[float, ...]:
        return tuple(state.heading_true_rad for state in self.states)

    @property
    def tracks_true_rad(self) -> tuple[float, ...]:
        return tuple(state.track_true_rad for state in self.states)

    @property
    def true_airspeeds_mps(self) -> tuple[float, ...]:
        return tuple(state.true_airspeed_mps for state in self.states)

    @property
    def ground_speeds_mps(self) -> tuple[float, ...]:
        return tuple(state.ground_speed_mps for state in self.states)

    @property
    def vertical_speeds_mps(self) -> tuple[float, ...]:
        return tuple(state.vertical_speed_mps for state in self.states)

    @property
    def fuel_remaining_kg(self) -> tuple[float, ...]:
        return tuple(state.fuel_remaining_kg for state in self.states)

    @property
    def weights_kg(self) -> tuple[float, ...]:
        return tuple(state.weight_kg for state in self.states)

    @property
    def evidence(self) -> tuple[EvidenceKind, ...]:
        return tuple(dict.fromkeys(kind for state in self.states for kind in state.evidence))

    @property
    def source_citations(self) -> tuple[SourceCitation, ...]:
        return tuple(
            dict.fromkeys(citation for state in self.states for citation in state.source_citations)
        )


@dataclass(frozen=True, slots=True)
class SimulationResult:
    trajectory: Trajectory
    outcome: SimulationOutcome
    termination_event: "TerminationEvent | None"
    model_name: str
    mode: str
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", tuple(self.notes))


# Import only for runtime dataclass annotation resolution, after class definitions
# to avoid a trajectory/termination import cycle.
from sr22_course_simulator.simulation.termination import TerminationEvent  # noqa: E402
