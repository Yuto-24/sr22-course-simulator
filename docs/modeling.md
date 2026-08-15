# Modeling Policy

## 1. Modeling level

The simulator is intentionally positioned between a purely kinematic drawing tool and a full 6-DoF flight-dynamics simulator.

The preferred approach is a **performance-based / semi-empirical model** built from:

- Aviation College training Reference Data;
- SR22 Chapter 5 performance data;
- physical relationships that are independently well-defined, such as coordinated-turn geometry, wind-vector addition and fuel/weight bookkeeping.

The model should reproduce the behavior relevant to training-course analysis without pretending to infer undocumented aerodynamic derivatives.

## 2. Inputs and state

### Flight inputs

The normal pilot-relevant input set is:

- Pitch
- Bank
- PWR
- Flap

Do not introduce yoke deflection, control-surface deflection or rudder input unless a future requirement actually needs them.

### Heading

Heading is a state quantity, not a continuous primary control input.

`Initial Heading` is part of InitialState. A `Target Heading` may exist as a goal or termination condition for a maneuver segment.

### Altitude

Altitude is likewise a state quantity. `Target Altitude` is a goal or termination condition, not a direct control.

### Coordinated flight assumption

For the current scope, ordinary maneuvers assume ideal coordinated flight. Yaw / rudder is solved implicitly by that assumption and is not exposed as a command.

Intentional sideslip, including Forward Slip, is explicitly outside the current scope. Preserve the architecture so a sideslip state/input can be added later without rewriting unrelated code.

## 3. Weight and fuel

Weight belongs to aircraft state, not Environment.

Initial loading must provide enough information to determine initial gross weight and usable fuel. During integration:

```text
fuel(t + dt) = fuel(t) - fuel_flow(t) * dt
weight(t)    = non_fuel_weight + remaining_fuel_weight(t)
```

The exact fuel-density convention and any unusable-fuel treatment must be sourced and documented.

Do not hold aircraft weight constant when the active performance model provides fuel flow and the simulated duration is long enough for fuel burn to matter.

## 4. Fixed configuration assumptions

For the target SR22 training configuration:

- Gear is fixed and therefore not represented as a variable state or input.
- The nose wheel pant / fairing is assumed removed throughout the simulation.
- Performance effects of this configuration must come from an explicit source-backed correction when available.

Do not silently apply a guessed wheel-pant correction.

## 5. Performance-table interpolation

The SR22 POH / approved flight-manual Chapter 5 tables should be treated as a multidimensional performance data set rather than isolated lookup pages.

Where supported by source data, build interpolators over independent variables such as:

- pressure altitude
- temperature / ISA deviation
- power
- weight, if the table or an approved correction supplies it
- configuration

Dependent quantities may include:

- TAS
- fuel flow
- climb rate
- climb time
- climb distance
- climb fuel
- descent / cruise quantities where published

Interpolation must stay inside the supported source domain unless an explicit, reviewed extrapolation rule exists. Default behavior is **no extrapolation**.

## 6. What multidimensional POH interpolation can and cannot provide

Multidimensional interpolation can provide a substantial part of the model, especially for **quasi-steady operating points**. It is therefore a first-class modeling method in this project.

However, an interpolated performance table is not automatically a complete arbitrary-state dynamic model. A source table usually describes selected stabilized conditions and may not independently span every combination of Pitch, Bank, PWR and Flap.

Accordingly:

- use POH interpolation directly where the requested quantity is represented by the table dimensions;
- use Aviation College Reference Data to anchor nominal Pitch / Bank / PWR / Flap operating points for training maneuvers;
- use physical equations for turn geometry, wind and state propagation;
- interpolate between source-backed operating points when the source coverage supports it;
- do not manufacture a unique TAS or vertical speed for arbitrary undocumented combinations merely because numerical interpolation is possible.

The initial implementation should favor a **quasi-steady segment model**. Transient acceleration and attitude-transition models can be added later when sufficient evidence or calibration data exists.

## 7. Suggested quasi-steady interpretation

For a commanded flight segment:

```text
Pitch / Bank / PWR / Flap
          +
Altitude / Temperature / Weight
          |
          v
Performance / Reference model
          |
          +--> airspeed
          +--> vertical speed or flight-path angle
          +--> fuel flow
          |
          v
Coordinated-turn + wind equations
          |
          v
Position / Heading / Altitude / Fuel / Weight
```

When the source data defines a nominal maneuver point rather than a continuous surface, the implementation should explicitly mark that result as reference-based or calibrated rather than pretending it is a direct POH lookup.

## 8. Wind

Ground velocity is the vector sum of air-relative velocity and wind velocity.

Meteorological wind direction is the direction **from which** the wind blows. Conversion code must be tested against canonical cases such as 270/20 producing an eastward wind vector.

Wind models should be polymorphic:

- NoWind
- ConstantWind
- altitude-dependent wind
- future spatial / temporal forecast wind, e.g. MSM

## 9. Reference Path vs Trajectory

Never conflate these objects.

- **Reference Path**: desired geometry, independent of wind.
- **Trajectory**: time-history generated by the aircraft model in an environment.

A path-following solver may compute commands that make Trajectory track Reference Path, but the two remain distinct and should be visualizable together.

## 10. NAV calculations

NAV calculations should use the same vector and wind conventions as the simulator.

For cut-angle / intercept work, define Cut Angle geometrically with respect to desired **ground track / reference course** unless a source explicitly defines another convention. With wind present, solve the heading required to produce that ground track.

The NAV layer should eventually provide:

- desired course / track
- WCA
- required heading
- GS
- cut/intercept course
- intercept point
- cut flight time
- gain/loss time where required

## 11. Model fidelity labels

Simulation outputs should retain enough metadata to identify how they were obtained, for example:

- `source_table_interpolated`
- `training_reference`
- `physics_derived`
- `calibrated`
- `assumed`

This is important for aviation training use: a numerically smooth answer must not obscure the strength of its underlying evidence.
