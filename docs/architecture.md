# Architecture

## 1. Scope

This project models SR22 training-flight trajectories, maneuver guidance, airport/reference paths and NAV problems at a level useful for pilot training.

It is intentionally positioned between:

- a purely kinematic path-drawing tool; and
- a full 6-DoF engineering flight-dynamics simulator.

The core external flight-input abstraction is:

- Pitch
- Bank
- PWR
- Flap

Heading, airspeed, vertical speed, ground track, position, altitude, fuel and weight are state or derived quantities.

Training maneuvers are **not** defined by the chapter-end `Reference Data` tables. They are defined from the training-procedure narrative and applicable general rules.

## 2. Three primary workflows

### 2.1 Direct-input forward simulation

Given an initial aircraft state, environment and pilot-relevant flight input, propagate the aircraft state.

```text
InitialState + Environment + FlightInput
                    |
                    v
             AircraftModel
                    |
                    v
               Trajectory
```

Typical use cases:

- "What happens if Pitch/Bank/PWR/Flap are held or changed this way?"
- wind/no-wind comparison;
- sensitivity analysis;
- controlled numerical experiments.

A direct-input experiment is not automatically equivalent to the official training maneuver even if its inputs resemble the chapter-end Reference Data row.

### 2.2 Procedure-driven maneuver guidance

Given a source-derived `ManeuverSpec`, environment and aircraft model, determine the flight inputs required to satisfy the actual maneuver targets and constraints.

```text
ManeuverSpec
     + Environment
     + AircraftModel
           |
           v
     Guidance / Control Logic
           |
           v
 Pitch / Bank / PWR / Flap
           |
           v
   Forward Simulation
           |
           v
      Trajectory
```

Typical use cases:

- Spiral Descent while respecting source-defined speed, path and bank constraints;
- Basic Flight where source-defined control relationships determine how deviations are corrected;
- ground-reference maneuvers where Bank changes with wind/path error.

### 2.3 Reference-path guidance

Given a pure geometric path and environment, calculate the flight inputs required to maintain that path.

```text
ReferencePath + Environment + AircraftModel
                    |
                    v
              GuidanceSolver
                    |
                    v
       Pitch / Bank / PWR / Flap
                    |
                    v
             ForwardSimulation
```

This workflow is used for:

- airport traffic patterns;
- KML-defined paths;
- NAV legs/intercepts;
- ideal ground-reference paths.

The geometric `ReferencePath` does not move with wind. Wind changes the required aircraft state/input and the resulting trajectory.

## 3. Principal domain objects

### `InitialState`

Initial aircraft conditions and loading needed to start integration.

At minimum:

- time;
- geographic or local position;
- altitude;
- heading;
- airspeed;
- initial fuel quantity;
- non-fuel/loading data sufficient to determine initial gross weight.

Current weight is derived from loading plus current fuel. Weight is not an Environment property.

Depending on future performance requirements, CG may become part of loading/state if a source-backed model actually requires it. Do not add it merely for completeness.

### `Environment`

External atmosphere and wind.

At minimum:

- wind vector;
- temperature;
- pressure / pressure altitude as required by active performance data.

Future implementations may add:

- position-dependent atmosphere;
- altitude-dependent wind;
- time-dependent wind;
- forecast providers such as MSM.

### `FlightInput`

Primary pilot-relevant inputs:

- `pitch_deg`;
- `bank_deg`;
- `power_pct`;
- `flap`.

Heading is not a normal `FlightInput`.

- Initial heading belongs to `InitialState`.
- Target heading may be a `Goal` or `TerminationCondition`.
- In path-following/NAV work, required heading is a derived guidance quantity/state target, not a replacement for Bank dynamics.

### `AircraftState`

Expected time-varying state / derived quantities include:

- time;
- position;
- altitude;
- heading;
- track;
- IAS/CAS/TAS where supported;
- GS;
- vertical speed / flight-path angle where supported;
- pitch;
- bank;
- PWR;
- flap;
- fuel remaining;
- fuel burned;
- current aircraft weight.

### `ManeuverSpec`

Source-derived definition of a training maneuver.

It contains semantics, not merely numbers.

Expected fields:

- source section and revision;
- objective;
- phases;
- targets;
- nominal values;
- approximate initial settings;
- control relationships;
- path constraints;
- safety limits;
- environment-dependent adjustment rules stated by the source;
- termination/completion conditions;
- attached advisory Reference Data.

See `docs/maneuver-specification.md`.

### `AdvisoryReference`

A separately stored chapter-end Reference Data row.

It is **not** part of the authoritative maneuver definition and must not silently drive the aircraft model.

Permitted uses:

- solver initialization;
- UI hints;
- result comparison;
- sanity checking;
- source traceability.

### `AirportSpec` / `RunwaySpec`

`AirportSpec` keeps AIP-derived airport metadata, a reference-only ARP,
Magnetic Variation and directional runway records. `RunwaySpec` keeps both
thresholds, threshold elevations, dimensions, True Bearing and source
provenance.

The ARP is not a runway-geometry origin. Every runway computes:

```text
RWY Center Point = (threshold_a + threshold_b) / 2
```

Runway vectors and left/right normals use the directional True Bearing. The
reciprocal direction reverses the threshold roles and runway vector while
retaining the same computed center point.

### `ReferencePath`

A geometric 2D/3D path independent of wind.

Typical forms:

- straight leg;
- circular arc;
- spiral / helix;
- traffic pattern;
- NAV leg sequence;
- ground-reference maneuver geometry.

### `Trajectory`

Time-indexed aircraft states generated by simulation. It must remain distinct from both `ReferencePath` and `ManeuverSpec`.

### `Goal` / `TerminationCondition`

Possible termination conditions include:

- elapsed time;
- target altitude;
- target heading;
- accumulated turn angle;
- target position;
- Reference Path intercept;
- leg endpoint;
- source-defined maneuver completion event;
- source-defined safety stop condition.

## 4. Performance architecture

The aircraft response model is composed from several layers.

```text
Canonical POH Performance Data
          |
          v
Multidimensional Interpolators
          |
          v
Published Performance Queries
          |
          +-------------------+
                              |
Procedure Targets       Analytical Physics
                              |
          +-------------------+
          |
          v
Quasi-steady Aircraft Response / Guidance
          |
          v
State propagation
```

### 4.1 POH performance layer

This is the principal quantitative source for published aircraft performance.

Examples of possible queries, only where source data supports them:

```text
pressure altitude x OAT/ISA deviation x PWR -> TAS
pressure altitude x OAT/ISA deviation x PWR -> fuel flow
pressure altitude x OAT/ISA deviation x weight -> climb performance
```

The exact independent variables must come from the actual applicable table, not from an API design wish list.

### 4.2 Physics layer

Use source-independent analytical relationships only where they are well-defined and compatible with the intended model.

Examples:

- coordinated-turn turn rate/radius;
- vector wind addition;
- coordinate transformations;
- state integration;
- fuel mass and weight update.

### 4.3 Procedure layer

The maneuver procedure supplies what the pilot is trying to maintain and how the source says deviations should be corrected.

Example:

```text
Basic Flight narrative:
    altitude correction -> Pitch
    speed correction    -> Power
```

This must not be replaced by fixed values from the Reference Data table.

### 4.4 Model coverage

Not every arbitrary `Pitch x Bank x PWR x Flap` combination is guaranteed to be resolvable from published data.

The aircraft model must expose coverage/status metadata such as:

- fully source-supported;
- POH-interpolated;
- physics-derived;
- calibrated;
- assumption-dependent;
- unsupported/out-of-domain.

Unsupported combinations must fail explicitly rather than returning fabricated smooth numbers.

## 5. Segment architecture

Maneuvers may be composed from reusable segments, but segment boundaries must follow the source semantics rather than forcing every maneuver into the same template.

A segment may contain:

- direct `FlightInput`; or
- a source-derived guidance rule;
- inherited initial state;
- target(s);
- control relationship(s);
- one or more termination conditions.

Examples of segment roles:

- preparation;
- entry;
- established maneuver;
- transition;
- recovery / completion.

A value stated only for Entry must not become a maneuver-wide constant.

## 6. Coordinate systems

Use SI units internally.

Recommended local integration frame:

- East [m];
- North [m];
- Up [m].

Geographic coordinates are used at interfaces and for KML output.

Angles in numerical routines should be radians unless explicitly documented otherwise. Public aviation-facing interfaces may use degrees.

Track / heading calculations must clearly state True vs Magnetic reference. Core physical simulation should prefer True reference; magnetic conversion belongs in navigation/interface logic.

Airport Reference Points are reference-only. Airport traffic-pattern geometry
uses the applicable RWY Center Point, source-backed True Bearing and SI
along-runway/lateral displacements. Magnetic Variation is not used to place KML
coordinates.

## 7. SR22 target configuration assumptions

For current project scope:

- landing gear is fixed; no Gear state/input is modeled;
- the target Aviation College configuration assumes the nose wheel pant / fairing is removed at all times;
- ordinary maneuvers assume coordinated flight;
- explicit Rudder / beta dynamics are not modeled;
- Forward Slip and intentional sideslip remain future scope.

Some supplied training documents contain Gear-related fields/procedures. Source transcriptions may preserve those fields for provenance, but the core target-aircraft model does not gain a variable Gear state from them.

Any performance effect associated with wheel-fairing configuration must come from an applicable explicit source or declared model assumption. Do not hide a guessed correction in the performance layer.

## 8. Suggested package structure

```text
src/sr22_course_simulator/
├── airport/
│   └── spec.py
├── aircraft/
│   ├── state.py
│   ├── input.py
│   ├── loading.py
│   ├── fuel.py
│   └── model.py
├── environment/
│   ├── atmosphere.py
│   └── wind.py
├── procedure/
│   ├── maneuver.py
│   ├── phase.py
│   ├── semantics.py
│   └── advisory_reference.py
├── performance/
│   ├── poh.py
│   ├── interpolation.py
│   ├── coverage.py
│   └── provenance.py
├── path/
│   ├── reference.py
│   ├── line.py
│   ├── arc.py
│   ├── spiral.py
│   └── traffic_pattern.py
├── guidance/
│   ├── maneuver.py
│   ├── path_following.py
│   ├── wind_correction.py
│   └── intercept.py
├── simulation/
│   ├── integrator.py
│   ├── segment.py
│   └── trajectory.py
├── nav/
│   ├── wind_triangle.py
│   ├── leg.py
│   ├── turn.py
│   └── cut_angle.py
├── export/
│   ├── kml.py
│   └── csv.py
└── plotting/
    ├── plot2d.py
    └── plot3d.py
```

Suggested data layout:

```text
data/
├── procedure/
│   ├── maneuver_specs/
│   └── reference_tables/      # advisory only
├── poh/
│   ├── canonical/
│   └── metadata/
└── airports/
```

This is a design target. Do not create empty modules/directories before they have a concrete use.

## 9. Initial implementation mapping

The package follows the domain-oriented layout above and creates modules only when exercised by implemented workflows:

```text
aircraft       FlightInput, loading/fuel, InitialState/AircraftState, response protocols
environment    atmosphere, terrain and polymorphic wind providers
performance    canonical tables, loader, interpolation, POH cruise query
maneuver       source-semantic ManeuverSpec and separate AdvisoryReference
airport        AirportSpec / RunwaySpec, DMS parsing and RWY Center Point
data/airports  canonical RJFM AIP transcription
path           wind-independent pylon, polyline and traffic-pattern geometry
guidance       wind triangle and bounded Spiral Descent guidance
simulation     analytical mechanics, termination, forward integrator, Trajectory
export         single/multi-placemark KML for ReferencePath and Trajectory
plotting       optional object-based 2D/altitude/3D views
```

There are intentionally no empty `nav`, forecast-weather, sideslip, Rudder, Gear-dynamics or 6-DoF modules.

### 9.1 Forward versus guided entry points

`ForwardSimulator.simulate` / `simulate_forward` accepts only:

```text
InitialState + Environment + FlightInputSource + AircraftResponseModel
             + TerminationCondition + SimulationConfig
```

It cannot read a `ManeuverSpec` or an `AdvisoryReference`.

`simulate_guided_spiral_descent` creates a `SpiralDescentGuidance` from an authoritative `ManeuverSpec` and a separate `PylonSpiralPath`, then delegates the resulting Pitch/Bank/PWR/Flap commands to the same forward integrator. Its result retains `reference_path`, `maneuver_spec`, `guidance_history` and `simulation.trajectory` as distinct typed objects.

### 9.2 Current response-model boundary

The response-model protocol resolves quasi-steady TAS, flight-path angle and mass fuel flow. The integrator alone applies coordinated-turn mechanics, wind addition, geographic propagation and fuel/weight bookkeeping.

No bundled POH table covers the Spiral Descent response point. The executable example therefore composes:

- `AssumedSteadyPointProvider`, whose local Pitch/PWR-to-TAS and PWR-to-fuel-flow parameters are all caller-supplied;
- `AssumedAngleOfAttackClosure`, which explicitly assumes `flight_path_angle = Pitch - reference angle of attack`;
- analytical coordinated-turn and wind-vector physics.

Those assumptions are retained as `assumed` evidence in every generated state. `SourceDataRequiredPerformanceProvider` provides an explicit unsupported path when a source-backed provider is required but absent.

### 9.3 Container boundary

The multi-stage `Dockerfile` has a dependency-free runtime target and a separate deterministic-test target. Both run directly from the same `src` tree with `PYTHONPATH=/app/src`; this avoids an online package-install step and still packages the canonical POH JSON alongside the code. The runtime executes as a non-root user and writes optional exports only through `/output`. `compose.yaml` maps that boundary to the host `artifacts/` directory without adding source PDFs or generated products to the image.

### 9.4 Coordinate and integration method

The initial integrator uses fixed time steps, midpoint heading for horizontal displacement, and a short-distance spherical local-tangent geographic approximation. It linearly interpolates a threshold-crossing final state so an altitude safety boundary is not numerically overshot. Heading is wrapped only for state display; `accumulated_turn_rad` remains unwrapped for 720-degree termination.
