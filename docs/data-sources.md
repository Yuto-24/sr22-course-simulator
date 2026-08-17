# Data Sources and Interpolation

## 1. Source policy

This project must preserve both **source provenance** and **source semantics**.

A numeric value is not meaningful unless the model also knows what role it has:

- target;
- limit;
- nominal value;
- approximate initial setting;
- advisory reference;
- published aircraft performance;
- derived/calibrated/assumed value.

Do not replace aviation-specific source material with generic assumptions merely because the latter are easier to model.

## 2. Role-based source authority

### 2.1 Aviation College student training procedures — narrative/body

Use the applicable body text and general chapter sections as the primary source for:

- maneuver purpose;
- maneuver sequence and phases;
- target speed/altitude/path/course;
- which input is used to correct which quantity;
- environment/wind judgement and source-defined correction method;
- nominal maneuver values;
- limits;
- minimum training altitude;
- entry, recovery and completion conditions.

The primary current document is the single-engine commercial-course student training procedure, revision 19, including Chapter 4 and Chapter 5 narrative sections.

### 2.2 SR22 approved flight manual / type-certified flight manual / POH

Use the applicable approved aircraft manual as the primary source for:

- aircraft limitations;
- published performance;
- performance-table applicability;
- configuration-specific corrections where published.

Chapter 5 Performance Data is expected to become the principal quantitative data source for the quasi-steady aircraft-performance layer.

### 2.3 Operational/local source documents

Airport-specific procedures, Aviation College operating procedures, airspace rules and other supplied operational material should be treated as the authority for their own operational domain.

Do not infer a local traffic pattern or local rule from generic aviation knowledge when an applicable source exists.

AIP airport/runway data and local pattern rules have different roles. AIP data
defines ARP metadata, thresholds, runway dimensions, elevations, True Bearing
and Magnetic Variation. The applicable operating material defines pattern
altitude and leg dimensions. Derived center points, runway vectors and normals
must be deterministic geometry rather than separately transcribed coordinates.

ARP is retained for reference and checks only. Runway and traffic-pattern
geometry uses the midpoint of the two source thresholds as RWY Center Point.

### 2.4 Analytical physics

Use independently well-defined physics/geometry to connect source-backed quantities:

- coordinated-turn relationships;
- wind-vector addition;
- path geometry;
- coordinate transformations;
- numerical integration;
- fuel mass / aircraft weight bookkeeping.

### 2.5 Chapter-end Aviation College Reference Data

Advisory only. See below.

### 2.6 Real-flight data / calibration

Future calibration may be used for explicitly identified model gaps. Keep calibration data and source-based canonical data separate.

## 3. Role of the training-procedure narrative

The narrative should be converted into machine-readable `ManeuverSpec` records before building maneuver controllers.

Recommended data flow:

```text
source PDF narrative
      |
      v
manual/verified semantic extraction
      |
      v
ManeuverSpec
      |
      +--> targets
      +--> limits
      +--> phases
      +--> control relationships
      +--> path constraints
      +--> termination conditions
      +--> source metadata
```

The goal is not to reproduce every sentence as data. Encode only the semantics needed by simulation/guidance while retaining source location metadata.

Suggested representation:

```text
ManeuverSpec
├── maneuver
├── source_document
├── source_revision
├── source_section
├── objective
├── safety_constraints
├── phases[]
│   ├── targets
│   ├── nominal_values
│   ├── initial_settings
│   ├── limits
│   ├── control_relationships
│   ├── path_constraints
│   └── exit_conditions
└── advisory_reference_id
```

## 4. Role of Chapter 4 / Chapter 5 Reference Data

The training document explicitly describes these values as `Reference` and states that Pitch / Power are generally values for standard-atmosphere conditions and vary with weight and external environment such as temperature and altitude.

The project therefore treats each row as `AdvisoryReference`, not as a maneuver definition or aircraft-performance measurement.

Suggested representation:

```text
AdvisoryReference
├── maneuver
├── phase
├── airspeed
├── pitch
├── bank
├── power
├── flap
├── raw_source_fields
├── source_document
├── source_revision
└── source_location
```

Permitted uses:

- numerical initial guess;
- UI hint;
- sanity check;
- computed-vs-reference comparison;
- source traceability.

Do **not** use Reference Data as:

- a regular multidimensional aircraft-performance surface;
- the authoritative definition of what a maneuver must hold;
- a fixed command profile when the body text says to maintain a different quantity;
- an undocumented fill-in for missing POH relationships.

If narrative and Reference Data appear inconsistent, preserve both and flag the discrepancy. Do not silently choose the Reference Data value.

## 5. Role of POH Chapter 5

Chapter 5 is the primary source for quantities published as functions of operating conditions.

Build machine-readable canonical tables before interpolation logic.

Recommended data flow:

```text
source PDF/table
      |
      v
raw transcription / extraction
      |
      v
validated canonical table
      |
      v
interpolator
      |
      v
runtime performance query
```

Never edit canonical source values merely to make interpolation easier.

## 6. Interpolation policy

### 6.1 General

- Prefer piecewise-linear / multilinear interpolation initially.
- Use higher-order interpolation only when demonstrated useful and non-overshooting.
- Do not extrapolate by default.
- Exact source-table nodes must reproduce source values within numerical precision.
- Interpolation axes and units must be explicit.
- Preserve source and interpolation status for every returned value.

### 6.2 Multidimensional surfaces

Typical surfaces may include, **only where the source actually supports them**:

```text
pressure_altitude x temperature x PWR -> TAS
pressure_altitude x temperature x PWR -> fuel_flow
pressure_altitude x temperature x weight -> climb_rate
```

Other surfaces may be constructed when supported by a set of compatible published tables.

Before combining tables across another dimension, verify:

- same dependent-variable definition;
- same aircraft/configuration applicability;
- same or compatible weight basis;
- same atmosphere/temperature convention;
- compatible power definition;
- compatible units;
- no hidden change in procedure/condition.

### 6.3 Cross-table interpolation

It is acceptable to create a new dimension from multiple compatible source tables if the tables represent the same physical quantity under the same definitions and differ only in the candidate independent variable.

The transformation must be documented and testable.

Do not create a Pitch or Bank dimension merely because chapter-end training Reference Data contains Pitch/Bank values.

## 7. Model coverage and out-of-domain behavior

Every performance query should be able to report:

- source data set/table;
- applicable source domain;
- whether the result is exact table data or interpolation;
- whether any additional physics/correction was applied;
- whether the request is unsupported/out-of-domain.

Default behavior outside canonical source coverage is **reject / explicit unsupported**, not silent extrapolation.

If an extrapolation is intentionally introduced later, it must be:

- explicit;
- separately labeled;
- justified;
- tested;
- disabled by default unless the project owner decides otherwise.

## 8. Weight treatment

Weight changes during flight due to fuel burn.

Initial loading must provide enough information to determine initial gross weight and fuel.

Where fuel flow is available:

1. query fuel flow for the current operating condition;
2. integrate fuel burn over the time step;
3. update fuel quantity;
4. update current aircraft weight;
5. use updated weight in subsequent performance queries when the active source/model supports weight dependence.

If a POH table is published at a fixed weight and no documented correction exists, preserve that applicability limitation.

## 9. Fuel flow and conversion

Keep fuel volume, fuel mass, flow and aircraft weight units explicit.

Any fuel-density conversion must have:

- a documented source; or
- an explicitly declared project convention.

Do not hide a density constant inside an unrelated conversion function.

## 10. Fixed target-aircraft configuration

Current project assumptions:

- target aircraft is SR22;
- Gear is fixed and not a variable model input/state;
- Nose Wheel Pant / Fairing is assumed removed.

If the applicable POH contains a performance correction for the relevant wheel-fairing configuration, encode it as a dedicated, sourced transformation.

If no source-backed correction is available, do not guess one.

Source documents may contain Gear fields/procedures. Preserve them in raw source transcription if needed for provenance, but mark them non-modeled/not-applicable to the current core aircraft configuration rather than making Gear dynamic.

## 11. Recommended data layout

```text
data/
├── procedure/
│   ├── maneuver_specs/
│   │   ├── chapter4/
│   │   └── chapter5/
│   ├── reference_tables/
│   │   ├── chapter4.yaml   # advisory only
│   │   └── chapter5.yaml   # advisory only
│   └── metadata.yaml
├── poh/
│   ├── canonical/
│   │   ├── cruise.csv
│   │   ├── climb.csv
│   │   └── ...
│   ├── metadata/
│   └── derived/            # optional reproducible caches, never canonical
└── airports/
    ├── rjfm.py
    └── ...
```

Do not commit generated dense grids as if they were canonical source data.

## 12. Provenance requirements

Every source-backed data set should carry:

- source title;
- revision / issue / effective date where available;
- chapter/section/page/table identity;
- extraction/transcription method;
- units;
- semantic role;
- applicability conditions;
- transformations;
- reviewer/manual corrections where applicable.

Any manual correction to extracted data must be visible in version control.

## 13. Recommended source semantic tags

Use explicit tags where practical:

```text
procedure_target
procedure_limit
procedure_nominal
procedure_initial_setting
procedure_control_relationship
procedure_path_constraint
advisory_reference
poh_table_value
poh_interpolated
physics_derived
calibrated
assumed
unsupported
```

These tags are part of the safety/traceability design, not cosmetic metadata.

## 14. Sources verified for the initial implementation

### 14.1 Training procedure

Primary file inspected outside the repository:

```text
本文_改正19.pdf
SHA-256: f00fea1903a235491e2079085bc0e65031497bd65d5ace2b471e19d00f96e0e8
```

The PDF revision table identifies 改正19, effective 2026-06-24. The implementation transcribes these locations:

| Role | Source page | PDF page | Page date |
|---|---:|---:|---:|
| Chapter 5 safety / minimum training height | 5-(1) | 124 | 2026-03-02 |
| Spiral Descent wind, clearing, entry | 5-(34) | 157 | 2020-12-16 |
| Spiral Descent execution, 720°, recovery | 5-(35) | 158 | 2020-12-16 |
| Chapter 5 advisory Reference Data | 5-(49) | 172 | 2023-07-06 |

The source contains Gear actions. They remain visible in the citation notes and advisory raw value, but do not become a dynamic Gear input/state for the fixed-gear target model.

### 14.2 Approved SR22 performance data

Primary file inspected outside the repository:

```text
SR22_G6_型式証明飛行規程(R5.8.28)全章.pdf
P/N 13772-006J
approval/effective date shown: 2023-08-28
SHA-256: 2a3ff005f213df01c55d5cfd7b3cbc6172037c89db60eb70700526e280949ac4
```

The initial canonical package data is a verified 2D slice of Cruise Performance p.5-32 (PDF page 192):

```text
fixed applicability: 2,000 ft pressure altitude, 2,500 RPM, 3,400 lb, no wind
axes:                MAP [inHg] x ISA deviation [degC]
outputs:             PWR [%], KTAS [kt], fuel flow [US gal/h]
```

The three dependent quantities are stored in separate immutable JSON tables under `src/sr22_course_simulator/data/poh/canonical/`. The printed rows were reordered from descending to ascending MAP with matching dependent-value reordering; that transformation is recorded in each citation. Canonical volumetric fuel flow remains GPH—no hidden fuel-density conversion is applied.

The printed POH note says to subtract 10 KTAS with the nose-wheel pant/fairing removed. The canonical table retains the printed baseline. Target-configuration correction is a separate sourced transformation and must never alter canonical values.

The current Chapter 5 has no descent-performance table covering 110 kt, approximately 10% Power, and 45–55 degrees Bank. Cruise data at 3,400 lb cannot be repurposed into a weight correction or arbitrary Spiral Descent response surface.

### 14.3 RJFM airport and runway data

The task supplied a transcription from `RJFM__20260301.pdf`, effective
2026-03-01, for RJFM AD 2.2 and AD 2.12. The raw PDF was not present in the
checkout or task attachment directory during implementation, so the canonical
Python record explicitly says `task-provided transcription` rather than
claiming independent PDF verification.

The record includes ARP, airport elevation, Magnetic Variation and annual
change, directional runway True Bearings, dimensions, threshold positions and
threshold elevations. Compact DMS is parsed deterministically. RWY Center Point,
measured threshold distance, runway vectors and normals are derived values and
are not separately transcribed.

The Aviation College operating-material values for 1000 ft MSL, 1.5 NM
downwind offset and 1.2 NM base extension are kept in a separate
`TrafficPatternSpec` source role. The 0.0 NM crosswind extension is labeled as
an explicit task assumption.

## 15. Canonical JSON schema

The strict version-1 loader requires:

```text
schema_version
table_id
axes[]: name, unit, strictly increasing values
output: name, unit
flat row-major values (last axis fastest)
citation: document/revision/date/chapter/section/page/table/extraction/transformations
applicability: aircraft/configuration/conditions
```

It rejects duplicate JSON keys, unknown fields, sparse/ragged grids, non-finite values, duplicate/descending axes and shape mismatch. Query coordinates must match the axis set exactly. Source endpoints are inclusive; any request outside the source domain raises structured `OutOfDomainError`. There is deliberately no extrapolation switch.
