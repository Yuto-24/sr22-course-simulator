# Validation

## 1. Validation philosophy

Aviation-related numerical outputs must be traceable, testable and semantically faithful to their sources.

The simulator should validate separate layers independently:

- source transcription fidelity;
- source semantic interpretation;
- POH table fidelity;
- interpolation fidelity;
- analytical-physics correctness;
- fuel/weight propagation;
- maneuver-model validity;
- guidance/path-following performance;
- export/visualization integrity.

Do not treat visual plausibility as sufficient validation.

## 2. Source-semantic validation

### 2.1 Maneuver narrative

Every encoded `ManeuverSpec` should be checked against the applicable narrative/body section.

Tests/review should verify that the implementation correctly distinguishes:

- target;
- limit;
- nominal value;
- approximate initial setting;
- control relationship;
- path constraint;
- termination/completion condition.

A value must not change semantic class merely because a numeric API is easier to implement that way.

### 2.2 Reference Data separation

Each encoded chapter-end Reference Data row should reproduce the source row exactly as an `AdvisoryReference`, but it must remain separate from the authoritative `ManeuverSpec`.

Required regression behavior:

- changing an advisory Reference Data value must not silently change a narrative-defined target or limit;
- a Reference Data-only value must not become a controller target unless explicitly promoted by a reviewed model rule;
- maneuver code must not be generated solely from a Reference Data row.

### 2.3 Conflict handling

If narrative and Reference Data appear inconsistent:

- preserve both;
- expose the discrepancy;
- use the applicable narrative for maneuver semantics unless another governing source clearly controls that semantic role;
- do not silently reconcile the values.

## 3. Minimum numerical tests

### Straight flight

- No wind, zero bank: ground track remains straight for a supported steady-state case.
- Constant wind: ground velocity equals air-relative velocity plus wind vector.
- Canonical wind convention: 270/20 produces an eastward wind component.

### Coordinated turn

For supported coordinated-turn cases, verify turn-rate/turn-radius relationships against the analytical model used by the simulator.

For a constant-bank no-wind test, the horizontal path should close to the expected circle within integration tolerance after a complete turn when other model assumptions make the analytical comparison valid.

### Altitude propagation

For a segment with analytically known constant vertical speed or flight-path angle, verify altitude against the analytical result.

Do not use such a synthetic test to claim that arbitrary Pitch/PWR combinations are validated.

### Fuel and weight

- fuel quantity must not increase absent an explicit refueling event;
- integrated fuel burn under constant fuel flow must match analytical value;
- current aircraft weight must decrease consistently with fuel mass burned;
- initial weight must be reproducible from initial loading/fuel inputs.

## 4. POH performance-table validation

For every canonical/interpolated POH data set:

- exact source-table nodes reproduce canonical values;
- axes and units are verified;
- table applicability metadata is retained;
- interpolation stays within neighboring values where the local source behavior warrants that expectation;
- requests outside source domain fail or return explicit out-of-domain status by default;
- generated/cached grids are reproducible from canonical data;
- cross-table interpolation is tested at source-table slices;
- no training Reference Data is used to fabricate a missing POH dimension.

## 5. Model-coverage tests

The model must be honest about unsupported operating regions.

Tests should verify that:

- source-supported cases resolve;
- out-of-domain POH queries reject by default;
- unsupported `Pitch / Bank / PWR / Flap` combinations do not return fabricated outputs;
- explicitly calibrated/assumed regions are labeled as such;
- model-status metadata survives through simulation results where practical.

## 6. Reference Path tests

Reference Path generation is validated independently from aircraft simulation.

Examples:

- straight-line endpoints and course;
- arc center, radius and sweep angle;
- traffic-pattern leg continuity;
- ground-reference geometry;
- KML longitude/latitude/altitude ordering.

Wind must not alter the Reference Path object itself.

## 7. Guidance tests

Path/procedure-driven guidance should expose tracking metrics where applicable:

- cross-track error (XTE);
- along-track error;
- altitude error;
- heading/track difference;
- speed error;
- path/pylon distance error for applicable ground-reference maneuvers.

Guidance tests should verify source-defined control intent where feasible.

Example:

- if the applicable procedure assigns Bank to ground-path correction, a path-error correction test should affect Bank rather than silently changing the reference geometry.

For calm-wind reference cases, verify that the guidance solution reduces to the appropriate simpler geometry.

## 8. Spiral Descent validation strategy

Spiral Descent should be validated in layers.

### Source layer

Verify encoding of the applicable Chapter 5 narrative, including the semantic distinction among:

- target/entry 110 kt;
- approximate entry Power;
- nominal Bank;
- maximum Bank;
- minimum training altitude;
- pylon/wind-related path behavior.

Do not validate the maneuver by checking only that output matches the chapter-end `Pitch / PWR / Bank` row.

### Physics layer

Validate coordinated-turn geometry and wind-vector behavior independently.

### Guidance layer

Verify that wind/path error produces the intended path-maintenance response and that limits are respected.

### Forward-input experiment

A separate test may hold `Pitch / Bank / PWR` constant and verify numerical propagation. Label this as direct-input simulation, not procedure-conformance validation.

## 9. NAV tests

Validate:

- zero-wind `heading == desired track` where magnetic variation is not part of the test;
- wind triangle against independent vector calculation;
- WCA sign conventions;
- Cut Angle geometric construction;
- required heading for a desired wind-corrected cut ground track;
- intercept point/time;
- gain/loss-time formulas where implemented.

True/Magnetic references must be explicit in test names/data.

## 10. Comparison with real flight data

Future calibration/validation may use recorded SR22 flight data.

When introduced:

- keep raw data immutable;
- separate calibration and validation flights;
- record aircraft/configuration/date/environment where relevant;
- compare time histories, not only endpoints;
- retain source-based canonical behavior;
- do not tune to one flight and call the model generally validated.

## 11. Validation priority

Initial practical sequence:

1. source-semantic extraction tests for Basic Flight and Spiral Descent;
2. POH canonical table-node reproduction;
3. POH multidimensional interpolation;
4. fuel/weight propagation;
5. wind vectors and straight-flight geometry;
6. coordinated-turn geometry;
7. Spiral Descent direct-input numerical experiment;
8. Spiral Descent procedure-driven guidance;
9. KML trajectory/reference export;
10. traffic-pattern reference geometry;
11. wind-corrected path following;
12. NAV Cut Angle / intercept calculations.

## 12. Tolerances

Numerical tolerances must be chosen per test category and documented in the test itself.

Avoid a single broad tolerance that can conceal regressions, source-transcription mistakes or model-coverage errors.

## 13. Executable validation suite

The initial implementation uses deterministic standard-library `unittest` tests, so validation does not depend on a plotting stack.

Run all tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The same suite can be run in the portable container test target:

```bash
docker compose build
docker compose run --rm test
```

This target contains only the source package, canonical bundled JSON and tests. It does not depend on a host Python installation, editable install, plotting stack or source PDFs.

The Docker build validates the interpreter resolved by `PYTHON_VERSION` and fails explicitly below the package minimum of Python 3.11. A static regression test keeps the Dockerfile, Compose default and `requires-python` metadata aligned.

Current regression groups cover:

- exact unit conversions and angle wrapping;
- canonical meteorological wind directions, including `270/20 -> East` and `000/20 -> South`;
- analytical coordinated-turn rate/radius/load factor;
- no-wind straight flight, wind-vector addition, constant-bank turns, vertical propagation and unwrapped accumulated turn;
- fuel-flow integration, non-increasing fuel and current-weight reduction;
- immutable canonical tables, strict loading, exact source nodes, N-dimensional interior interpolation, derived-grid separation and explicit out-of-domain rejection;
- verified POH cruise source nodes and source-backed target-configuration correction separation;
- source-semantic Spiral Descent transcription, advisory isolation, Bank limit and phase-specific Power behavior;
- Reference Path wind independence and pylon projection;
- KML `longitude,latitude,altitude` order, coordinate count, altitude retention and XML escaping.

The runnable demonstration is also exercised as a smoke test, but its plausible shape is not treated as aircraft-model validation. Its assumption evidence must survive in the resulting `Trajectory`.

## 14. Current validation limits

Passing tests establish implementation correctness against the encoded sources, analytical equations and explicitly declared assumptions. They do not validate the assumption-dependent Spiral Descent response as actual SR22 performance. That requires an applicable source relationship or separately identified calibration/validation flight data.
