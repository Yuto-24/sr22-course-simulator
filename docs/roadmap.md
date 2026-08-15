# Roadmap

## Near-term priorities

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

- define runway geometry and training-specific Reference Paths from applicable source procedures;
- export traffic-pattern KML;
- generate wind-corrected guidance required to maintain the same ground path;
- support airport-specific procedures as data rather than hard-coded special cases where practical;
- keep path geometry separate from aircraft trajectory.

### NAV solver

#### Calm-wind NAV

- leg geometry;
- course/track relationship;
- turn/intercept geometry;
- Cut Angle flight time.

#### Forecast-wind NAV

- WCA;
- required heading;
- GS;
- wind-corrected Cut Angle / intercept;
- intercept time;
- gain/loss time where required.

Use the same vector/wind conventions as the trajectory simulator.

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
