# Roadmap

## Near-term priorities

### 1. Core state and units

Implement the common domain model first:

- InitialState
- AircraftState
- FlightInput
- Environment
- Trajectory
- unit conversion utilities
- wind-vector conventions
- fuel / weight propagation

### 2. Performance data layer

- encode Aviation College Chapter 4 / Chapter 5 Reference Data;
- extract and validate SR22 Chapter 5 performance tables;
- implement source-domain-aware multidimensional interpolation;
- preserve source metadata and applicability limits.

### 3. Spiral Descent practical version

Initial user-facing practical feature:

- initial position / altitude / heading / airspeed / fuel / weight;
- Pitch / Bank / PWR / Flap;
- constant or no-wind environment;
- 3D trajectory;
- heading, track, GS, TAS, VS, altitude, fuel and weight history;
- configurable termination by altitude / heading / turn count / time;
- 2D and 3D visualization.

### 4. KML export

Export both:

- Reference Path;
- Simulated Trajectory.

KML should preserve altitude when a 3D representation is meaningful.

## Subsequent features

### Training maneuvers

Generate calm-wind and wind-affected trajectories for applicable training maneuvers using the common segment/performance architecture.

Likely candidates include:

- Steep Turn
- Slow Flight
- climb / descent / constant-rate or constant-speed phases
- landing / traffic-pattern related segments where sufficient source data exists

Do not add a maneuver merely by inventing missing performance behavior.

### Airport traffic patterns

- define runway geometry and training-specific Reference Paths;
- export traffic-pattern KML;
- generate wind-corrected guidance inputs to maintain the same ground path;
- support airport-specific procedures as data rather than hard-coded special cases where practical.

### NAV solver

Calm-wind NAV:

- leg geometry;
- heading / track relationship;
- turn / intercept geometry;
- Cut Angle flight time.

Forecast-wind NAV:

- WCA;
- required heading;
- GS;
- wind-corrected Cut Angle / intercept;
- intercept time;
- gain/loss time where required.

### Weather integration

Future integration with forecast wind fields such as JMA MSM:

- interpolate wind by position, altitude and time;
- keep the wind provider independent from the aircraft model;
- prohibit silent extrapolation beyond the weather-data domain.

### Flight-data comparison

- import recorded trajectory / flight data;
- overlay reference, simulation and actual flight;
- compute tracking and performance differences;
- use selected data for calibration without destroying source-based behavior.

## Future / explicitly out of current scope

Keep architectural room for, but do not implement prematurely:

- Forward Slip / intentional sideslip;
- explicit rudder / beta modeling;
- full transient longitudinal/lateral stability derivatives;
- control-surface deflection models;
- full 6-DoF dynamics;
- pilot neuromuscular/control-loop simulation.
