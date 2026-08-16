# Modeling Policy

## 1. Modeling level

The simulator is intentionally positioned between a purely kinematic drawing tool and a full 6-DoF flight-dynamics simulator.

The preferred approach is a **performance-based / semi-empirical, quasi-steady model** built from:

- Aviation College training-procedure narrative for maneuver semantics and control intent;
- SR22 Chapter 5 performance data as the main quantitative performance source;
- analytical physical relationships such as coordinated-turn geometry, vector wind addition and fuel/weight propagation;
- explicit calibration only where needed and traceable.

The end-of-chapter Aviation College `Reference Data` tables are **not** the baseline aircraft model and are **not** the authoritative maneuver definition.

## 2. Inputs and state

### Flight inputs

The normal pilot-relevant input set is:

- Pitch;
- Bank;
- PWR;
- Flap.

Do not introduce yoke deflection, control-surface deflection or Rudder input unless a future requirement actually needs them.

### Heading

Heading is a state quantity, not a continuous primary control input.

`Initial Heading` is part of `InitialState`. A `Target Heading` may exist as a goal or termination condition.

When the desired object is a ground track or path, guidance may compute a required heading/turn target from wind and path geometry, but Heading is still propagated as state.

### Altitude

Altitude is a state quantity. `Target Altitude` is a goal/constraint, not a direct input.

### Coordinated-flight assumption

For the current scope, ordinary maneuvers assume ideal coordinated flight. Rudder/Yaw coordination is implicit and not exposed as a command.

Intentional sideslip, including Forward Slip, is explicitly outside current scope. Preserve architecture so a sideslip state/input can be added later without rewriting unrelated code.

## 3. Maneuver semantics come from the narrative

The training procedure must be parsed into semantic roles rather than treated as a table lookup.

For each maneuver/phase, distinguish:

- target;
- limit;
- nominal value;
- approximate initial setting;
- control relationship;
- path constraint;
- environment-dependent correction rule;
- entry/exit/termination condition;
- advisory Reference Data.

Example from Chapter 5 Basic Flight narrative:

```text
altitude correction -> Pitch
speed correction    -> Power
```

This is a source-defined control relationship and is more important to the model than a chapter-end Pitch/Power pair.

The implementation must not assume that the same relationship applies to every maneuver. Use the applicable maneuver narrative.

## 4. Why Reference Data is advisory

The training procedure's general discussion of Power Setting/Pitch Attitude describes them as approximate indications used to obtain desired flight parameters and notes that they vary with weight and external environment.

The Chapter 4/5 `Reference Data` sections similarly state that Pitch and Power values are generally standard-atmosphere values, vary with weight/temperature/altitude, and should not be chased by instrument fixation.

Therefore a Reference Data row may be attached as:

```text
AdvisoryReference
```

but it must not automatically define:

- maneuver target;
- control law;
- required fixed input;
- aircraft performance surface.

A direct-input experiment may intentionally hold the row values, but it must be labeled as such and must not be presented as the official maneuver behavior.

## 5. Weight and fuel

Weight belongs to aircraft state, not Environment.

Initial loading must provide enough information to determine initial gross weight and usable fuel. During integration:

```text
fuel(t + dt) = fuel(t) - fuel_flow(t) * dt
weight(t)    = non_fuel_weight + remaining_fuel_weight(t)
```

The exact fuel-density convention and unusable-fuel treatment must be sourced/documented.

When the active performance model provides fuel flow, update fuel and weight continuously enough for the intended accuracy.

Current weight must be supplied to performance queries whenever the source table/model requires it.

If a published performance table applies at a particular weight and no documented correction exists, retain that applicability restriction. Do not invent a weight correction merely to keep the API continuous.

## 6. Fixed target-aircraft configuration

For the target SR22 training configuration:

- Gear is fixed and therefore not represented as a variable state/input;
- Nose wheel pant / fairing is assumed removed throughout simulation;
- coordinated flight is the ordinary assumption.

Some source material contains Gear fields or Gear-related procedure text. Preserve such content in source provenance where necessary, but do not infer a variable Gear model from it for this project.

Do not silently apply a guessed wheel-pant performance correction.

## 7. POH multidimensional interpolation

SR22 POH / approved-flight-manual Chapter 5 data is a first-class quantitative modeling source.

Where the source supports it, build multidimensional interpolators over actual source variables such as:

- pressure altitude;
- OAT / ISA deviation;
- PWR;
- weight, where supported directly or by a documented correction;
- flap/configuration, where a table actually defines it.

Dependent quantities may include:

- TAS;
- fuel flow;
- climb rate;
- climb time;
- climb distance;
- climb fuel;
- other published performance quantities.

### Interpolation rules

- canonical source data remains immutable;
- exact source nodes must reproduce source values;
- default is no extrapolation;
- units and axes are explicit;
- generated dense grids are derived artifacts and reproducible;
- prefer piecewise linear / multilinear interpolation first;
- combine tables only after confirming compatible definitions and applicability;
- provenance follows every performance result.

## 8. What POH interpolation contributes to the motion model

POH multidimensional interpolation can provide a substantial portion of a useful quasi-steady aircraft model. It should be treated as a **primary performance provider**, not merely a correction layer on top of training Reference Data.

A useful architecture is:

```text
current state
+ environment
+ applicable PWR/configuration
        |
        v
POH performance query
        |
        +--> TAS / performance quantity where published
        +--> fuel flow where published
        +--> climb/descent performance where published
        |
        v
analytical physics + maneuver constraints
        |
        v
state propagation
```

However, POH tables do not automatically define every arbitrary combination of Pitch, Bank, PWR and Flap as an unconstrained transient dynamics model.

In particular, if Pitch is not an independent variable in the source performance data, the implementation must not pretend that interpolating unrelated tables creates a validated `Pitch -> TAS/VS` law.

Instead, connect Pitch to the motion model only through one of:

1. a source-defined control relationship / maneuver target;
2. an analytically defensible relationship with all required quantities available;
3. an explicit, documented calibration/model assumption;
4. a supported quasi-steady operating-region model.

Otherwise mark the requested operating point unsupported.

## 9. Model-coverage philosophy

The external API can still expose:

```text
FlightInput = Pitch / Bank / PWR / Flap
```

while the initial aircraft-response model supports only a subset of that state space.

Every quantitative result should be able to report a coverage/fidelity status, for example:

- `poh_table_value`;
- `poh_interpolated`;
- `procedure_target`;
- `physics_derived`;
- `calibrated`;
- `assumption_dependent`;
- `unsupported`;
- `out_of_domain`.

Do not widen model coverage by using Reference Data as undocumented filler.

## 10. Quasi-steady segment interpretation

The preferred initial implementation is phase/segment based.

A source-derived maneuver phase may look conceptually like:

```text
Targets / constraints
    IAS / altitude / path / turn geometry

Initial or nominal settings
    approximate PWR / nominal Bank / etc.

Control relationships
    error in controlled quantity -> Pitch / Bank / PWR adjustment

Aircraft response
    POH performance + physics

Termination
    source-defined completion / target / safety event
```

This structure allows inputs to change as required by wind, weight and atmosphere while still preserving the procedure's actual objective.

## 11. Spiral Descent interpretation

The Chapter 5 narrative is a useful example of why this design matters.

The source provides elements including:

- wind judgement;
- a pylon/reference relationship;
- entry aiming for 110 kt at pylon abeam;
- approximate 10% Power during entry;
- nominal 45-degree Bank with a maximum of 55 degrees;
- a minimum training altitude of AGL 2,000 ft.

These are not semantically equivalent numbers.

The model should classify them as target, initial setting, nominal value, limit and path/safety constraint as applicable.

Do not implement the official maneuver by holding the chapter-end `Pitch=-1`, `Bank=45`, `PWR=10` values for the entire maneuver merely because the Reference Data row lists them.

That fixed-input case is valid only as a deliberate forward-simulation experiment.

## 12. Wind

Ground velocity is the vector sum of air-relative velocity and wind velocity.

Meteorological wind direction is the direction **from which** the wind blows.

Wind models should be polymorphic:

- `NoWind`;
- `ConstantWind`;
- altitude-dependent wind;
- future spatial/time-dependent forecast wind such as MSM.

Reference Path geometry is independent of wind.

## 13. Reference Path vs Trajectory

Never conflate these objects.

- **Reference Path**: desired ground geometry, independent of wind.
- **Trajectory**: time history generated by aircraft + environment + guidance/direct input.

A path-following solver computes inputs that make Trajectory track Reference Path, but both remain separately visible/exportable.

## 14. NAV calculations

NAV calculations should use the same vector/wind conventions as simulation.

For cut-angle/intercept work, define Cut Angle geometrically with respect to desired **ground track / reference course** unless a governing source explicitly defines another convention.

With wind present:

1. define the desired cut/intercept ground track;
2. solve required heading from wind triangle;
3. determine GS;
4. solve intercept geometry and time.

The NAV layer should eventually provide:

- desired course / track;
- WCA;
- required heading;
- GS;
- cut/intercept course;
- intercept point;
- cut flight time;
- gain/loss time where required.

## 15. Model fidelity metadata

Simulation outputs and intermediate values should retain semantic/provenance labels, including:

- `procedure_target`;
- `procedure_limit`;
- `procedure_nominal`;
- `procedure_initial_setting`;
- `advisory_reference`;
- `poh_table_value`;
- `poh_interpolated`;
- `physics_derived`;
- `calibrated`;
- `assumed`;
- `unsupported`.

This is essential for training use: numerical smoothness must not hide weak evidence or change the meaning of a source value.

## 16. Implemented Spiral Descent model coverage

The primary training PDF was inspected at source pages 5-(34) and 5-(35). The implemented specification now records:

- entry at a selected pylon with wind judgement and a normally tailwind-oriented setup;
- 110 kt at pylon abeam;
- approximately 10% Power as an Entry setting;
- approximately -1 degree Pitch as a descent-attitude reference, not a frozen command;
- 45-degree nominal Bank and 55-degree maximum Bank;
- Pitch control of 110 kt;
- Bank adjustment for Drift / pylon relationship / constant-radius correction;
- 720-degree turn completion and the AGL 2,000 ft contingency;
- the source recovery sequence.

The source passage says `110 kt` but the encoded passage does not establish IAS/CAS/TAS. The `ManeuverSpec` therefore uses `AirspeedKind.UNSPECIFIED`. Current guidance runs only when its configuration explicitly acknowledges an assumption that interprets this value as TAS. No implicit IAS-to-TAS conversion exists.

The current SR22 G6 POH Chapter 5 was also inspected. It contains cruise, climb and other published performance data, but no descent-response surface covering the Spiral Descent state. Consequently:

- the production-safe response path remains unsupported for that state;
- the runnable example is explicitly assumption-dependent;
- the chapter-end training Reference Data is not used to close Pitch/PWR/Bank performance gaps;
- coordinated-turn geometry, wind addition and fuel/weight integration remain analytical and independently testable.

The minimal guidance controller uses source-defined semantic roles but has assumption-labeled gains. Entry Power is used only during the configured Entry interval; established Power is a separate caller-supplied assumption. Bank corrections are clipped at the source maximum. The present run stops at 720 degrees or the minimum-height boundary and does not yet propagate the full Recovery phase.
