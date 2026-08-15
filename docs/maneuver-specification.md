# Maneuver Specification

## 1. Purpose

Training maneuvers must be modeled from the narrative procedure in the Aviation College student training procedures, not from the end-of-chapter `Reference Data` table.

The narrative defines what the maneuver is trying to achieve, which quantities are to be kept, what the pilot changes to keep them, what limits apply, and when the maneuver starts or ends.

The `Reference Data` table is retained only as an advisory reference because the document itself states that Pitch and Power are approximate values and vary with weight and external conditions.

## 2. Maneuver definition is not a row of numbers

A maneuver definition is a structured control problem.

Recommended shape:

```text
ManeuverSpec
├── identity
│   ├── name
│   ├── chapter_section
│   └── source_revision
├── objective
├── prerequisites
├── safety_constraints
├── phases[]
│   ├── name
│   ├── entry_conditions
│   ├── targets
│   ├── control_relationships
│   ├── nominal_or_initial_settings
│   ├── limits
│   ├── environment_adaptation
│   └── exit_conditions
├── termination_conditions
└── advisory_reference
```

The fields above should be encoded only where the source supports them.

## 3. Semantic classes of values

Do not store every source number as the same kind of value.

### `target`

A quantity the procedure says to maintain or achieve.

Examples:

- target airspeed;
- target altitude;
- desired path;
- desired ground-track relationship to a pylon;
- target course or heading when explicitly specified.

### `limit`

A value that must not be exceeded or crossed.

Examples:

- maximum bank;
- minimum training altitude;
- maximum normal descent rate;
- airspeed/configuration limits.

### `nominal`

A normal or standard value explicitly stated in the maneuver body, while still allowing adjustment.

Example: a standard bank that may be changed for path correction.

### `initial_setting`

An approximate value used to enter or establish a condition, not a requirement to freeze that value for the entire maneuver.

Example: `Power about 10%` during Spiral Descent entry.

### `control_relationship`

A source-backed statement describing which pilot-relevant input is used to correct a controlled quantity.

Example from Basic Flight:

```text
altitude error -> Pitch correction
speed error    -> Power correction
```

This is often more important than the approximate Pitch/Power values in the Reference Data table.

### `advisory_reference`

A value appearing only in the chapter-end Reference Data table, or a value whose table presentation is explicitly described as a reference/approximation.

It may be displayed, used as an initial numerical guess, or used for a sanity check. It must not silently become a maneuver target, controller setpoint, or aircraft-model truth.

## 4. Source precedence inside a maneuver

For maneuver definition:

1. use the maneuver narrative/body;
2. use general chapter rules that apply to the maneuver;
3. use aircraft limitations/performance from the applicable AFM/POH for aircraft behavior and limits;
4. use chapter-end Reference Data only as advisory context.

If two source locations appear inconsistent, preserve both with provenance and flag the conflict for review. Do not silently choose whichever value is easier to implement.

## 5. Example: Basic Flight

The Chapter 5 Basic Flight narrative states that straight-and-level flight maintains altitude, airspeed and heading, and explicitly states the basic correction relationship:

```text
altitude correction -> Pitch
speed correction    -> Power
```

Therefore a guidance implementation should represent the controlled quantities and correction relationship directly.

It should not implement Basic Flight as a fixed Pitch and fixed Power taken from the Reference Data table.

## 6. Example: Spiral Descent

The Chapter 5 Spiral Descent narrative provides, among other items:

- judge the wind;
- choose a pylon and normally enter with a tailwind-oriented setup;
- lead so that the aircraft is 110 kt at pylon abeam;
- set Power to approximately 10% during entry;
- use 45 degrees bank with a maximum of 55 degrees;
- comply with the Chapter 5 minimum training altitude for Spiral Descent, AGL 2,000 ft.

These have different semantics:

```text
110 kt             -> target / entry target according to phase
about 10% PWR      -> approximate initial setting
45 deg bank        -> nominal maneuver value
55 deg bank        -> limit
AGL 2,000 ft       -> safety constraint
pylon relationship -> path / guidance constraint
wind judgement     -> environment-dependent behavior
```

The maneuver should therefore not be implemented as:

```text
Pitch = -1 deg
Bank  = 45 deg
PWR   = 10%
```

for the entire maneuver merely because the Reference Data row contains those values.

A forward-simulation experiment may intentionally hold those inputs constant, but that experiment must be labeled as a direct-input simulation, not as "the training-procedure Spiral Descent".

## 7. Reference Data attachment

A maneuver may carry the matching Reference Data row as a separate object:

```text
AdvisoryReference
├── airspeed
├── pitch
├── power
├── bank
├── flap
└── provenance
```

This object has no authority to override the narrative `ManeuverSpec`.

Recommended uses:

- initial guess for a numerical solver;
- UI hint;
- comparison against computed required input;
- plausibility/sanity check;
- historical/source traceability.

Prohibited uses without additional justification:

- defining the maneuver solely from the row;
- interpolating sparse Reference Data into an aircraft response surface;
- forcing the controller to hold table Pitch/Power instead of the actual target quantity;
- treating table values as independent aerodynamic measurements.

## 8. Path-driven guidance

For a maneuver with a desired ground path:

```text
ManeuverSpec / ReferencePath
        +
Environment
        +
AircraftModel
        |
        v
GuidanceSolver
        |
        v
Pitch / Bank / PWR / Flap
```

The guidance solver should use the source-defined relationships where available.

Examples:

- course/track maintenance under wind -> required heading/track relationship;
- pylon/path error -> Bank correction when the source assigns Bank to path control;
- altitude/path error -> Pitch and/or Power according to the applicable source procedure;
- airspeed error -> use the source-defined correction method for that maneuver or phase.

Do not assume one universal Pitch/Power control law for every maneuver.

## 9. Phase-specific behavior

Many training procedures are sequences, not one stabilized condition. Keep phases explicit.

Examples:

- preparation;
- entry;
- established maneuver;
- transition;
- recovery / completion.

A value such as `Power about 10%` may belong only to Entry. Encoding it as a maneuver-wide constant changes the meaning of the procedure.

## 10. Implementation rule

Before implementing a new training maneuver, an agent must:

1. read the applicable narrative section;
2. read the applicable general chapter rules;
3. identify targets, limits, control relationships, approximate settings and phase transitions;
4. check applicable AFM/POH limitations/performance data;
5. encode the `ManeuverSpec` with source metadata;
6. attach Reference Data only as advisory information;
7. add tests that verify the encoded procedure semantics.

If the source does not say how a missing relationship should behave, mark the model gap explicitly instead of filling it from the Reference Data table.

## 11. Encoded Spiral Descent transcription

The initial implementation verified the primary 改正19 PDF and represents the maneuver as three phases.

### Entry — source 5-(34), PDF page 157

- wind judgement and Clearing;
- set a Pylon and normally arrange tailwind entry;
- lead for 110 kt at Pylon abeam (`Target`, airspeed kind retained as `UNSPECIFIED`);
- approximately 10% Power (`InitialSetting`);
- rough trim to maintain altitude;
- Pylon-abeam relationship (`PathConstraint`).

### Execution — source 5-(35), PDF page 158

- establish 110-kt descent attitude at Pylon abeam;
- approximately -1 degree Pitch (`InitialSetting`, not a fixed target);
- 45 degrees Bank (`Nominal`, adjustable);
- 55 degrees absolute Bank (`Limit`);
- maintain 110 kt with Pitch (`ControlRelationship`);
- adjust Bank as altitude/wind changes to correct Drift and retain the ground-target relationship / constant radius (`ControlRelationship` and `PathConstraint`);
- complete 720 degrees (`TerminationSpec`).

### Recovery — source 5-(35), PDF page 158

- roll out and level at 720 degrees;
- if AGL 2,000 ft is reached first, hold altitude and continue to the prescribed heading before rollout;
- keep final altitude/heading, apply MAX Power smoothly, then perform Cruise Procedure and complete the call.

The current guidance simulator integrates Entry and Execution and stops at the 720-degree goal or a conservative minimum-AGL safety boundary. Recovery semantics are encoded, but Recovery propagation and the source minimum-altitude contingency are explicit `not_implemented` gaps.

### Advisory row — source 5-(49), PDF page 172

The exact row (A/S 110, Pitch -1.0, Power 10, Bank 45, Gear DOWN, Flaps UP) is held in a separate immutable `AdvisoryReference`. `SpiralDescentGuidance` accepts only `ManeuverSpec`, making it structurally impossible for that row to become its target/controller input.
