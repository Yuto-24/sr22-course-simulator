# AGENTS.md

This file defines project rules for AI coding agents and human contributors. Treat these rules as design constraints unless the repository owner explicitly changes them.

## 1. Project purpose

Build an SR22 training-course simulator that connects pilot-relevant flight inputs, training Reference Data, approved performance data, wind and navigation geometry.

The normal flight-input abstraction is:

- `Pitch`
- `Bank`
- `PWR`
- `Flap`

Do **not** turn the project into a full 6-DoF simulator unless explicitly requested.

## 2. Preserve the model boundaries

Keep these concepts distinct:

- `InitialState`: initial aircraft conditions including position, altitude, heading, airspeed, fuel/loading information.
- `Environment`: atmosphere and wind. Weight does not belong here.
- `FlightInput`: Pitch / Bank / PWR / Flap.
- `AircraftState`: time-varying aircraft quantities such as heading, TAS, GS, altitude, fuel and weight.
- `ReferencePath`: desired geometric path independent of wind.
- `Trajectory`: simulated time-history in an environment.
- `Goal` / `TerminationCondition`: Target ALT, Target HDG, elapsed time, accumulated turn, position, path intercept, etc.

Do not use `HDG` as a routine continuous command merely because an implementation shortcut would make it easier. Heading is normally a state. `Initial HDG` is required where absolute orientation matters; `Target HDG` may be a segment goal.

## 3. Aircraft configuration assumptions

Current target configuration:

- Cirrus SR22 training aircraft.
- Fixed landing gear: do not model Gear state/input.
- Nose wheel pant / fairing is assumed removed at all times.
- Ordinary maneuvers assume ideal coordinated flight.
- Rudder / beta is not a routine input.
- Forward Slip and intentional sideslip are future scope.

Do not add Gear or Rudder fields to core APIs without a requirement that justifies them.

## 4. Weight and fuel are dynamic aircraft state

Do not place `weight` in Environment.

The simulation must be able to determine initial total weight from loading/fuel information and reduce it as fuel is burned. When fuel flow is available, propagate:

```text
remaining fuel -> current fuel mass -> current aircraft weight
```

If a performance table only applies at a particular weight and no documented correction exists, expose that limitation. Do not invent a correction.

## 5. Source hierarchy and provenance

Primary planned aviation sources are:

1. Aviation College student training procedures, single-engine commercial course
   - Chapter 4 final Reference Data table
   - Chapter 5 final Reference Data table
2. SR22 approved flight manual / POH
   - Chapter 5 Performance Data

When implementing source-derived behavior:

- inspect the actual source before changing values or formulas;
- preserve terminology and applicability;
- record document/revision/page/table metadata where practical;
- distinguish source values from interpolation, physics-derived values, calibration and assumptions;
- never silently replace an aviation-specific source rule with generic aviation knowledge.

If a source does not support a requested value, say so in code comments/docs or return explicit unsupported/out-of-domain behavior rather than fabricating data.

## 6. POH interpolation policy

Multidimensional interpolation of Chapter 5 performance tables is a core technique and should be used aggressively where the source dimensions support the requested quantity.

Requirements:

- source-table nodes reproduce source values;
- no extrapolation by default;
- independent variables and units are explicit;
- canonical source values are stored separately from generated dense grids;
- generated grids must be reproducible;
- prefer simple multilinear interpolation unless evidence supports a more complex method;
- do not force sparse training Reference Data into a regular numerical surface without a defensible relationship.

A smooth interpolation result is not evidence that an arbitrary `Pitch x Bank x PWR x Flap` state is physically supported. Respect source coverage.

## 7. Modeling philosophy

Prefer a performance-based / semi-empirical, quasi-steady model first.

Use:

- training Reference Data for nominal maneuver operating points;
- POH performance surfaces for published condition-dependent quantities;
- analytical physics for coordinated-turn geometry, vector wind, state propagation and other well-defined relationships;
- calibration only when explicitly introduced and traceable.

Do not invent aerodynamic derivatives, control-surface models or transient behavior simply to make a simulation look realistic.

## 8. Reference Path and wind

Reference Path is desired ground geometry. Wind must not translate or deform the Reference Path itself.

For path-following work:

```text
ReferencePath + Environment + AircraftModel
    -> Guidance
    -> Pitch / Bank / PWR / Flap
    -> Trajectory
```

Always preserve the ability to display Reference Path and Trajectory separately.

## 9. NAV conventions

Use a common vector implementation for simulation and NAV calculations.

- Explicitly distinguish True and Magnetic references.
- Meteorological wind direction is FROM direction.
- For wind-corrected Cut Angle work, treat the geometric cut as desired ground track relative to the reference course unless the governing source defines otherwise.
- Solve the heading required to produce that track under wind.

## 10. Units

Use SI units internally unless there is a strong numerical reason not to.

Aviation-facing interfaces may use:

- ft
- kt
- NM
- fpm
- degrees
- % PWR

Keep conversion boundaries explicit. Do not mix degrees/radians or knots/m/s implicitly.

## 11. Testing requirements

Every numerical feature should have deterministic tests.

At minimum preserve tests for:

- no-wind straight flight;
- canonical wind-vector directions;
- constant-bank turn against the analytical model;
- altitude propagation for analytically known cases;
- fuel burn and weight reduction;
- exact POH table-node reproduction;
- out-of-domain interpolation rejection;
- Reference Path geometry independent of simulation;
- KML coordinate/altitude ordering.

A plot that looks reasonable is not a test.

## 12. Code organization

Prefer small domain-specific modules over a single large simulator file, but do not create empty architecture for its own sake.

Keep raw/canonical source data separate from code and derived caches.

Avoid hidden global state. Simulation results should be represented by a dedicated result / trajectory object rather than loose arrays when practical.

## 13. Documentation obligations

When changing a fundamental model assumption, update the relevant files under `docs/` and this `AGENTS.md` when the agent rule itself changes.

When adding source-backed data, document provenance and applicability.

When knowingly using an approximation, name it and document its limitation.

## 14. Current implementation priority

Unless a task says otherwise, prioritize work in this order:

1. common state / units / wind conventions;
2. source data ingestion and interpolation;
3. Spiral Descent practical 3D simulation;
4. KML export;
5. reusable maneuver segments;
6. calm/wind training maneuver trajectories;
7. airport traffic-pattern Reference Paths;
8. NAV / Cut Angle solver;
9. forecast-wind integration;
10. real-flight-data comparison/calibration.

## 15. Do not silently expand scope

The following are explicitly future scope and should not appear in core APIs prematurely:

- Forward Slip / intentional sideslip;
- explicit Rudder / beta;
- control-surface deflections;
- full 6-DoF equations;
- detailed transient stability/control models.

If one of these becomes necessary, propose the smallest compatible extension instead of restructuring the whole project without discussion.
