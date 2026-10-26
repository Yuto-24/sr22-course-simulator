# Roadmap

## Near-term priorities

### Current execution order (2026-09-25)

Traffic-pattern generalization is complete through Issues #8, #9 and #13 (merged by PR #14). Before this roadmap sync, there were no open implementation Issues.

Next execution order:

1. #15 — reusable NAV leg / wind-triangle solver.
2. #16 — Cut Angle / intercept solver and Jupyter workflow; depends on #15.
3. #17 — wind-corrected guidance targets for existing ReferencePath geometry; depends on #15 and may proceed in parallel with #16 after #15.
4. Expand source-backed aircraft-performance coverage when the required POH relationship/data is available.
5. Add flight-data comparison after the guidance/trajectory interfaces are stable enough to compare without introducing one-off adapters.

NAV is the immediate priority because it reuses the already-validated geometry and wind conventions and is not blocked by the unresolved longitudinal `Pitch/PWR/state -> TAS/flight-path-angle` relationship.

### Initial implementation status

Implemented baseline:

- common SI units, Initial/Aircraft state, Pitch/Bank/PWR/Flap input, wind, terrain, fuel and weight conventions;
- narrative-semantic `ManeuverSpec` and separately typed `AdvisoryReference`;
- strict canonical POH JSON ingestion and no-extrapolation N-dimensional interpolation;
- a verified 2,000-ft / 2500-RPM POH cruise slice and source/applicability metadata;
- explicit unsupported/assumption-dependent response boundaries;
- direct-input forward integration;
- minimal Entry/Execution Spiral Descent guidance with bounded Bank/path/wind correction;
- separate pylon Reference Path and simulated Trajectory;
- KML and optional plotting helpers;
- reusable Airport/Runway master data with ARP reference-only semantics and
  threshold-derived RWY Center Point;
- RJFM RWY09/RWY27 LEFT/RIGHT Make-Circle Reference Paths, Notebook and
  individual/combined Google Earth altitude KML export;
- generalized RJFM + seven additional RJF* airports into 32 LEFT/RIGHT Traffic Patterns with per-profile altitude/descent/provenance;
- Jupyter-first Kyushu Traffic Pattern workflow with per-airport KML/KMZ and aggregate `KYUSHU_TRAFFIC_PATTERNS.kmz`;
- deterministic numerical/source-semantic tests, including Notebook/KMZ contract coverage.

Still open before claiming source-backed SR22 Spiral Descent performance:

- identify or calibrate the longitudinal `Pitch/PWR/state -> TAS/flight-path-angle` relationship for the applicable descent region;
- source/implement a mass fuel-flow conversion applicable to the active cruise/descent data before using GPH in state propagation;
- implement the narrative AGL 2,000-ft contingency (hold altitude, continue to prescribed heading) rather than conservatively stopping;
- propagate the full rollout/level-off/Recovery phase;
- expand canonical POH transcription beyond the initial verified cruise slice;
- validate with independent flight data while preserving canonical source behavior.

### 1. Core state, units and environment

Implement the common domain model first:

- `InitialState`;
- `AircraftState`;
- `FlightInput`;
- `Environment`;
- `Trajectory`;
- unit conversion utilities;
- wind-vector conventions;
- fuel / weight propagation.

Important rules:

- Weight is aircraft state, not Environment.
- Initial loading/fuel must be sufficient to determine initial weight.
- Heading is state; Initial Heading belongs to InitialState.
- Core flight input is Pitch / Bank / PWR / Flap.

### 2. Maneuver source schema and narrative extraction

Before implementing training maneuvers, build the procedure-data layer.

- define `ManeuverSpec` schema;
- define semantic types: target / limit / nominal / initial setting / control relationship / path constraint / termination;
- encode source metadata;
- start with Chapter 5 Basic Flight and Spiral Descent;
- encode applicable general Chapter 5 minimum-training-altitude rules;
- encode Chapter 4 maneuver narratives as needed for traffic-pattern/landing work.

Do **not** start by turning Chapter 4/5 Reference Data rows into maneuver models.

### 3. Advisory Reference Data transcription

Encode Chapter 4 / Chapter 5 end-of-chapter Reference Data separately as `AdvisoryReference`.

Purpose:

- initial solver guess;
- display/reference;
- sanity checks;
- comparison against computed required inputs.

It must remain separate from `ManeuverSpec` and aircraft performance.

### 4. POH performance data layer

Build the main quantitative aircraft-performance provider.

- extract/validate SR22 Chapter 5 canonical performance tables;
- preserve table applicability and metadata;
- implement source-domain-aware multidimensional interpolation;
- verify exact source nodes;
- reject extrapolation by default;
- support cross-table dimensions only where definitions/configuration are compatible;
- expose model/source coverage metadata.

Initial high-value surfaces include, where published data supports them:

- altitude x temperature/ISA deviation x PWR -> TAS;
- altitude x temperature/ISA deviation x PWR -> fuel flow;
- climb performance versus applicable source variables.

### 5. Aircraft response / model-coverage layer

Connect POH performance to physical state propagation.

- define supported quasi-steady operating regions;
- implement explicit unsupported/out-of-domain behavior;
- connect coordinated-turn equations;
- connect wind-vector kinematics;
- connect fuel burn / weight update;
- document every non-POH assumption/calibration.

Do not claim complete arbitrary `Pitch x Bank x PWR x Flap` coverage until the missing relationships are actually justified.

### 6. Spiral Descent practical version

Implement two clearly distinct modes.

#### Direct-input experiment

Inputs:

- initial position / altitude / heading / airspeed / fuel/loading;
- Pitch / Bank / PWR / Flap;
- no-wind or constant-wind environment;
- termination by time / altitude / accumulated turn etc.

Outputs:

- 3D trajectory;
- heading / track;
- IAS/TAS as supported;
- GS / VS;
- altitude;
- fuel / current weight;
- model-status/provenance metadata.

This mode answers: "What happens with these inputs?"

#### Procedure-driven Spiral Descent

Use the Chapter 5 narrative `ManeuverSpec`.

- maintain source-defined speed/path relationships;
- model nominal vs maximum Bank separately;
- treat approximate entry Power as an initial setting rather than a maneuver-wide fixed constant;
- respect the applicable minimum training altitude;
- use wind/pylon path error in guidance according to source-defined intent;
- attach chapter-end Reference Data only for comparison.

This mode answers: "What inputs are required to perform the maneuver under this environment?"

### 7. KML export and visualization

Export both:

- Reference Path;
- Simulated Trajectory.

KML should preserve altitude when a 3D representation is meaningful.

Visualization should support overlay of:

- Reference Path;
- actual simulated trajectory;
- wind vector;
- heading/track vectors where useful;
- source target/limit traces;
- computed Pitch / Bank / PWR / Flap histories.

## Subsequent features

### Training maneuvers

Add maneuvers only after their narrative sections have been converted to `ManeuverSpec`.

Likely candidates:

- Basic Flight;
- Steep Turn;
- Slow Flight;
- climb / descent / level-off phases;
- applicable landing/traffic-pattern phases;
- ground-reference maneuvers.

For each maneuver:

1. encode narrative semantics;
2. identify POH-supported performance relationships;
3. identify analytical physics;
4. expose model gaps;
5. only then implement guidance/simulation.

Do not add a maneuver merely by copying its Reference Data row.

### Airport traffic patterns

- [x] define reusable AIP-derived Airport/Runway master data and deterministic DMS ingestion;
- [x] define RWY Center Point from reciprocal thresholds without using ARP as a geometry origin;
- [x] implement RJFM RWY09/RWY27 LEFT/RIGHT Make-Circle Reference Paths from supplied local dimensions;
- [x] derive turn radius from 110 KTAS and Bank, including 10 deg/s Roll transitions;
- [x] connect Base descent to a 3-degree Final ending at the runway-length-dependent Aiming Marker;
- [x] export four individual and one multi-Placemark Google Earth altitude-wall KML;
- [x] add verbatim task-provided RJFM Short Downwind and RWY27 Entry geometry plus a tangent 110 KTAS / 22-degree Circle;
- [x] load and validate canonical AIP geometry for RJFM and the seven other target airports (RJFO, RJFK, RJFT, RJFS, RJFU, RJFG, RJFC);
- [x] support per-runway LEFT/RIGHT profiles and Abeam / Base-turn-start / Base-turn-end descent semantics;
- [x] add the seven other airports' operational profiles and individual/combined KML generation (Issue #9);
- [x] add a Jupyter-first RJFM + seven-airport workflow and per-airport / aggregate KMZ export (Issue #13 / PR #14);
- [ ] generate wind-corrected guidance targets for the same wind-independent ground path (Issue #17);
- support airport-specific procedures as data rather than hard-coded special cases where practical;
- keep path geometry separate from aircraft trajectory.

### NAV solver

#### Core leg / wind-triangle solver — Issue #15

- straight-leg geometry;
- True Course / Track;
- TAS + wind -> WCA / required True Heading / GS;
- ETE;
- explicit rejection when the requested ground track is not flyable at the supplied TAS/wind.

#### Cut Angle / intercept — Issue #16

- Cut Angle defined against desired ground track / reference course;
- intercept geometry and intercept point;
- wind-corrected Heading / GS via #15;
- cut distance and flight time;
- gain/loss time only when the comparison baseline is explicit;
- Jupyter-first interactive workflow and visualization.

#### ReferencePath wind guidance — Issue #17

- local desired Track from existing ReferencePath geometry;
- WCA / required Heading / GS via #15;
- support current polyline, circular/pylon and traffic-pattern path forms;
- preserve ReferencePath coordinates unchanged by wind;
- keep guidance targets separate from full closed-loop Trajectory tracking.

Use the same vector/wind conventions as the trajectory simulator. After #15, #16 and #17 are intentionally independent enough to proceed in parallel.

### Weather integration

Future integration with forecast wind fields such as JMA MSM:

- interpolate wind by position, altitude and time;
- keep wind provider independent from aircraft model;
- prohibit silent extrapolation beyond weather-data domain;
- use the same Environment interface as constant/no-wind simulations.

### Flight-data comparison

- import recorded trajectory / flight data;
- overlay Reference Path, simulation and actual flight;
- compare state histories and guidance inputs;
- use selected data for explicitly labeled calibration;
- retain separate validation data;
- never overwrite canonical source data with fitted values.

## Future / explicitly out of current scope

Keep architectural room for, but do not implement prematurely:

- Forward Slip / intentional sideslip;
- explicit Rudder / beta modeling;
- full transient longitudinal/lateral stability derivatives;
- control-surface deflection models;
- full 6-DoF dynamics;
- pilot neuromuscular/control-loop simulation.

## Definition of done for a new maneuver

A maneuver is not considered implemented merely because a trajectory can be drawn.

Minimum completion criteria:

- governing narrative source identified;
- `ManeuverSpec` encoded;
- targets/limits/initial settings/control relationships correctly separated;
- applicable POH data identified;
- model gaps explicit;
- Reference Data attached only as advisory;
- deterministic tests added;
- source/model provenance visible in the implementation/documentation.
