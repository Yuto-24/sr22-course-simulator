# AGENTS.md

This file defines project rules for AI coding agents and human contributors. Treat these rules as design constraints unless the repository owner explicitly changes them.

## 1. Project purpose

Build an SR22 training-course simulator that connects:

- pilot-relevant flight inputs;
- Aviation College training-procedure narrative;
- SR22 approved performance data;
- wind and atmosphere;
- geometric Reference Paths;
- NAV calculations.

The normal flight-input abstraction is:

- `Pitch`
- `Bank`
- `PWR`
- `Flap`

Do **not** turn the project into a full 6-DoF simulator unless explicitly requested.

## 2. Critical source rule: do not build maneuvers from Reference Data tables

This rule is mandatory.

The Chapter 4 / Chapter 5 end-of-chapter `Reference Data` tables in the Aviation College student training procedures are **not the primary definition of a maneuver and are not the aircraft-model baseline**.

The training document states that Pitch and Power are approximate values for obtaining the desired flight parameters and change with weight and external environment. The Reference Data section likewise states that Pitch / Power are generally values for standard-atmosphere conditions, vary with weight, temperature and altitude, and should not be chased by instrument fixation.

Therefore:

- read the maneuver narrative/body before implementing the maneuver;
- derive maneuver targets, control relationships, phases, limits, path relationships and termination conditions from the narrative and applicable general sections;
- treat `Reference Data` values as advisory/reference values only;
- never convert sparse Reference Data rows into an aerodynamic/performance surface;
- never freeze Reference Data Pitch/Power values when the narrative says to maintain another quantity and adjust inputs to achieve it;
- never use a Reference Data row as the sole definition of a training maneuver.

Permitted uses of Reference Data:

- numerical solver initial guess;
- UI hint;
- computed-result comparison;
- sanity check;
- source traceability.

If a value exists only in Reference Data and not in the governing narrative/performance source, label it `advisory_reference`. Do not silently promote it to `target`, `limit`, `control law`, or `aircraft performance`.

## 3. Role-based source authority

Do not use one global source priority for every question. Use the source appropriate to the semantic role.

### Training maneuver procedure / control intent

Primary source:

- Aviation College student training procedures, applicable narrative/body and general sections.

This source defines, where stated:

- maneuver objective;
- phases and sequence;
- target airspeed/altitude/course/path;
- which quantity is corrected with Pitch, Power, Bank, etc.;
- nominal values and limits;
- minimum training altitude;
- entry/recovery/completion conditions.

### Aircraft performance and aircraft limitations

Primary source:

- applicable SR22 approved flight manual / type-certified flight manual / POH data.

Chapter 5 performance tables should provide the principal quantitative performance data where their applicability covers the requested state.

### Operational/local rules

Use the applicable Aviation College operating procedure, airport procedure, regulation, AIP-derived rule, or other explicitly supplied operational source. Do not infer local procedures from generic aviation knowledge.

### Analytical physics

Use physics for relationships that are independently defined and do not overwrite source-specific operational rules, including:

- coordinated-turn geometry;
- vector wind addition;
- coordinate geometry;
- state integration;
- fuel/weight bookkeeping.

### Reference Data tables

Advisory only, as described above.

### Calibration / real-flight data

May refine an explicitly identified model relationship, but must not erase the canonical source data or silently replace source-backed limits/procedures.

## 4. Preserve the model boundaries

Keep these concepts distinct:

- `InitialState`: initial aircraft conditions including position, altitude, heading, airspeed, fuel/loading information.
- `Environment`: atmosphere and wind. Weight does not belong here.
- `FlightInput`: Pitch / Bank / PWR / Flap.
- `AircraftState`: time-varying aircraft quantities such as heading, TAS, GS, altitude, fuel and weight.
- `ManeuverSpec`: source-derived definition of a training maneuver.
- `ReferencePath`: desired geometric path independent of wind.
- `Trajectory`: simulated time-history in an environment.
- `Goal` / `TerminationCondition`: Target ALT, Target HDG, elapsed time, accumulated turn, position, path intercept, etc.
- `AdvisoryReference`: chapter-end Reference Data attached for comparison/initialization only.

Do not use `HDG` as a routine continuous command merely because an implementation shortcut would make it easier. Heading is normally a state. `Initial HDG` is required where absolute orientation matters; `Target HDG` may be a segment goal.

## 5. ManeuverSpec is a control problem, not a lookup row

A maneuver implementation should distinguish at least:

- `target`: quantity to maintain/achieve;
- `limit`: value that must not be exceeded/crossed;
- `nominal`: normal value that may be adjusted;
- `initial_setting`: approximate entry/establishment value;
- `control_relationship`: which flight input corrects which controlled quantity;
- `path_constraint`: desired ground/reference geometry;
- `phase`: entry / established / transition / recovery etc.;
- `termination_condition`;
- `advisory_reference`.

Do not flatten these concepts into a single numeric configuration.

Before implementing a new training maneuver, read `docs/maneuver-specification.md` and the governing source narrative.

## 6. Aircraft configuration assumptions

Current target configuration:

- Cirrus SR22 training aircraft.
- Fixed landing gear: do not model Gear state/input.
- Nose wheel pant / fairing is assumed removed at all times.
- Ordinary maneuvers assume ideal coordinated flight.
- Rudder / beta is not a routine input.
- Forward Slip and intentional sideslip are future scope.

Do not add Gear or Rudder fields to core APIs without a requirement that justifies them.

Some supplied training material contains Gear-related fields/procedures. Preserve their provenance when transcribing source material, but do not turn them into variable aircraft state for this target fixed-gear model unless the repository owner explicitly changes this project assumption.

## 7. Weight and fuel are dynamic aircraft state

Do not place `weight` in Environment.

Initial loading/fuel must provide enough information to determine initial aircraft weight. During simulation, when fuel flow is available, propagate:

```text
remaining fuel -> current fuel mass -> current aircraft weight
```

The current performance query should receive current weight when weight is a supported variable or correction.

If a performance table applies at a particular weight and no documented correction exists, expose that limitation. Do not invent a weight correction.

## 8. POH interpolation is a primary quantitative modeling method

Multidimensional interpolation of applicable Chapter 5 performance data is a core aircraft-model technique and should be used wherever the source dimensions support the requested quantity.

Requirements:

- canonical source-table nodes reproduce source values;
- no extrapolation by default;
- independent variables and units are explicit;
- canonical source values are stored separately from generated dense grids;
- generated grids are reproducible;
- prefer simple multilinear interpolation initially unless evidence supports a different method;
- combine tables only when definitions, configuration and applicability are compatible;
- return provenance/model-coverage metadata with queried results.

POH interpolation is not merely a correction to training Reference Data. It is the primary quantitative performance provider for supported operating regions.

However, do not claim that a smooth POH surface automatically defines every arbitrary `Pitch x Bank x PWR x Flap` transient state. Respect what the published tables actually parameterize.

## 9. Unsupported operating regions must stay explicit

The public `FlightInput` API may remain `Pitch / Bank / PWR / Flap` even if the quantitative response model initially supports only part of that space.

When a requested combination cannot be justified by POH data, narrative procedure, analytical physics, or an explicitly documented calibration/model assumption:

- return/raise an explicit unsupported or model-gap result;
- document the missing relationship;
- do not manufacture a physically plausible-looking response;
- do not use Reference Data to conceal the gap.

Prefer a narrower honest model over a broad undocumented model.

## 10. Modeling philosophy

Prefer a performance-based / semi-empirical, quasi-steady model first.

Use:

- training-procedure narrative for maneuver semantics and control intent;
- POH performance surfaces for published condition-dependent quantities;
- analytical physics for coordinated-turn geometry, wind, state propagation and other well-defined relationships;
- explicit calibration only when introduced, documented and testable;
- Reference Data only as advisory context.

Do not invent aerodynamic derivatives, control-surface models or transient behavior merely to make simulation output look realistic.

## 11. Reference Path and wind

Reference Path is desired ground geometry. Wind must not translate or deform the Reference Path itself.

For path-following work:

```text
ManeuverSpec / ReferencePath + Environment + AircraftModel
    -> Guidance
    -> Pitch / Bank / PWR / Flap
    -> Trajectory
```

Always preserve the ability to display Reference Path and Trajectory separately.

For a source-defined ground-reference maneuver, encode the source's path-control method rather than assuming fixed Bank.

## 12. NAV conventions

Use a common vector implementation for simulation and NAV calculations.

- Explicitly distinguish True and Magnetic references.
- Meteorological wind direction is FROM direction.
- For wind-corrected Cut Angle work, treat the geometric cut as desired ground track relative to the reference course unless the governing source defines otherwise.
- Solve the heading required to produce that track under wind.
- Keep Reference Course / Track geometry separate from the wind-corrected Heading required to fly it.

## 13. Units

Use SI units internally unless there is a strong numerical reason not to.

Aviation-facing interfaces may use:

- ft
- kt
- NM
- fpm
- degrees
- % PWR

Keep conversion boundaries explicit. Do not mix degrees/radians or knots/m/s implicitly.

## 14. Provenance and semantic labels

Source-backed or modeled values should retain enough metadata to distinguish:

- `procedure_target`
- `procedure_limit`
- `procedure_nominal`
- `procedure_initial_setting`
- `advisory_reference`
- `poh_table_value`
- `poh_interpolated`
- `physics_derived`
- `calibrated`
- `assumed`
- `unsupported`

A numerically smooth answer must not obscure the strength or meaning of its evidence.

## 15. Testing requirements

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
- KML coordinate/altitude ordering;
- maneuver narrative transcription/semantics;
- source precedence: narrative procedure must not be overridden by advisory Reference Data;
- target/limit/initial-setting semantic separation.

A plot that looks reasonable is not a test.

## 16. Code organization

Prefer small domain-specific modules over one large simulator file, but do not create empty architecture for its own sake.

Keep these separately represented:

- canonical source data;
- training maneuver specifications;
- advisory Reference Data;
- POH performance data;
- generated interpolation products;
- simulation outputs.

Avoid hidden global state. Simulation results should use a dedicated result / trajectory object rather than loose arrays when practical.

## 17. Documentation obligations

When changing a fundamental model assumption, update the relevant files under `docs/` and this `AGENTS.md` when the agent rule itself changes.

When adding a maneuver:

- document the narrative source section;
- encode semantic roles of values;
- document model gaps;
- keep any Reference Data row advisory.

When adding source-backed performance data, document provenance and applicability.

When knowingly using an approximation, name it and document its limitation.

## 18. Current implementation priority

Unless a task says otherwise, prioritize work in this order:

1. common state / units / wind / fuel-weight conventions;
2. maneuver-source schema and narrative `ManeuverSpec` extraction;
3. canonical POH Chapter 5 data ingestion and multidimensional interpolation;
4. explicit model-coverage handling for supported/unsupported operating regions;
5. Spiral Descent practical 3D forward simulation and procedure-driven guidance;
6. KML export;
7. reusable maneuver/path segments;
8. calm/wind training-maneuver trajectories;
9. airport traffic-pattern Reference Paths;
10. NAV / Cut Angle solver;
11. forecast-wind integration;
12. real-flight-data comparison/calibration.

## 19. Do not silently expand scope

The following are explicitly future scope and should not appear in core APIs prematurely:

- Forward Slip / intentional sideslip;
- explicit Rudder / beta;
- control-surface deflections;
- full 6-DoF equations;
- detailed transient stability/control models;
- pilot neuromuscular/control-loop simulation.

If one becomes necessary, propose the smallest compatible extension instead of restructuring the whole project without discussion.
