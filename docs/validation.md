# Validation

## 1. Validation philosophy

Aviation-related numerical outputs must be traceable and testable. The simulator should separate:

- source-table fidelity;
- interpolation fidelity;
- physics-equation correctness;
- maneuver-model validity;
- path-following performance.

Do not treat visual plausibility as sufficient validation.

## 2. Minimum numerical tests

### Straight flight

- No wind, zero bank: ground track remains straight.
- Constant wind: ground velocity equals air-relative velocity plus wind vector.
- Canonical wind convention test: 270/20 produces an eastward wind component.

### Coordinated turn

For steady level coordinated turns, verify the implemented turn-rate / turn-radius relationships against the analytical solution used by the model.

For a constant-bank no-wind test, the simulated horizontal path should close to the expected circle within integration tolerance after one complete turn.

### Altitude propagation

For a model segment with known constant vertical speed or flight-path angle, verify altitude against the analytical result.

### Fuel and weight

- fuel quantity must never increase absent an explicit refueling event;
- fuel burn integrated over a constant fuel-flow test must match the analytical value;
- aircraft weight must decrease consistently with fuel mass burned.

## 3. Performance-table tests

For every interpolated POH data set:

- exact table nodes reproduce the canonical source values;
- interpolation stays within neighboring source bounds where monotonicity implies it should;
- requests outside the source domain fail or return an explicit out-of-domain result by default;
- units are tested;
- derived/cached grids are reproducible from canonical data.

## 4. Training Reference Data tests

Each encoded training reference must be checked against the corresponding source row / phase.

Do not silently normalize or alter source terminology if doing so would make later source verification harder.

## 5. Reference Path tests

Reference Path generation should be validated independently from aircraft simulation.

Examples:

- straight-line endpoints and course;
- arc center, radius and sweep angle;
- traffic-pattern leg continuity;
- KML coordinates / altitude ordering.

## 6. Guidance tests

Path-driven guidance should expose tracking error metrics, at least where applicable:

- cross-track error (XTE)
- along-track error
- altitude error
- heading / track difference

For calm-wind reference cases, verify that the guidance solution reduces to the expected simpler geometry.

## 7. Maneuver validation priority

Initial practical validation sequence:

1. straight flight
2. constant-bank turn
3. Spiral Descent in calm wind
4. Spiral Descent with constant wind
5. KML trajectory export
6. traffic-pattern reference geometry
7. wind-corrected path following
8. NAV cut-angle / intercept calculations

## 8. Comparison with real flight data

Future calibration may use recorded SR22 flight data. When this is introduced:

- keep raw flight data immutable;
- distinguish calibration data from validation data;
- record aircraft/configuration/date where relevant;
- compare state histories, not only final endpoints;
- avoid tuning to a single flight and calling the model validated.

## 9. Tolerances

Numerical tolerances must be chosen per test category and documented in the test itself. Avoid a single broad tolerance that can conceal regressions.
