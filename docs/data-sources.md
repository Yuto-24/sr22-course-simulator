# Data Sources and Interpolation

## 1. Authoritative source hierarchy

The simulator should preserve source provenance and avoid replacing aviation-specific source material with generic assumptions.

Primary planned sources:

1. Aviation College student training procedures for the single-engine commercial course
   - Chapter 4 final Reference Data table
   - Chapter 5 final Reference Data table
2. SR22 approved flight manual / POH
   - Chapter 5 Performance Data

Other sources may be added later, but each data set must record its document name, revision/effective date, page/table identity and any applicability notes.

## 2. Role of Aviation College Reference Data

The training Reference Data tables define nominal training operating points. They are intended to anchor quantities such as:

- airspeed
- pitch
- power
- bank where specified
- flap configuration
- maneuver / phase identity

These are training references, not universal aerodynamic laws. They should be modeled as named operating points or phase-specific reference records.

Suggested representation:

```text
TrainingReference
├── maneuver
├── phase
├── airspeed
├── pitch
├── bank
├── power
├── flap
├── source_document
├── source_revision
└── source_location
```

## 3. Role of POH Chapter 5

Chapter 5 is the primary performance source for quantities published as functions of operating conditions.

Build machine-readable tables before building interpolation logic. Keep the extracted/raw table values separate from interpolated/generated values.

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

Never edit the canonical source table merely to make interpolation easier.

## 4. Interpolation policy

### 4.1 General

- Prefer piecewise linear / multilinear interpolation initially.
- Use higher-order interpolation only when there is a demonstrated benefit and it does not introduce overshoot or nonphysical artifacts.
- Do not extrapolate by default.
- Exact source-table nodes must reproduce the source values exactly within numerical precision.
- Interpolation axes and units must be explicit.

### 4.2 Multidimensional surfaces

Typical interpolation surfaces may involve combinations such as:

```text
pressure_altitude x temperature x power -> TAS
pressure_altitude x temperature x power -> fuel_flow
pressure_altitude x temperature x weight -> climb_rate
```

Only use dimensions actually supported by the applicable table or an explicit approved correction.

### 4.3 Sparse or phase-based training data

The training Reference Data tables are likely to be sparse operating points rather than rectangular numerical grids. Do not force them into a regular multidimensional interpolator without a defensible model.

Instead, use them as:

- nominal targets;
- anchors for a maneuver model;
- validation points;
- calibration points for a quasi-steady relationship.

## 5. Weight treatment

Weight changes during flight due to fuel burn.

The performance-query interface should receive current aircraft weight when the source data or model requires it. If the underlying POH table is based on a specific weight and no approved correction exists, retain that applicability limitation in the result metadata.

Do not invent a weight correction solely to make the API continuous.

## 6. Fuel flow and mass propagation

Where fuel flow is available from the active performance surface:

1. query fuel flow for the current operating state;
2. integrate fuel burn over the time step;
3. update fuel quantity;
4. update aircraft weight;
5. use updated weight in subsequent performance queries when applicable.

Keep volume, mass and flow units explicit. Any fuel-density conversion must have a documented source or declared convention.

## 7. Fixed training-aircraft configuration

The model assumes the target training SR22 configuration, including the nose wheel pant / fairing being removed.

If the POH includes a published performance correction for wheel fairings / wheel pants, encode that correction in a dedicated, testable step and cite its source metadata in the data file. If no applicable source is loaded, do not guess the correction.

## 8. Data file organization

Suggested layout:

```text
data/
├── training_reference/
│   ├── chapter4.yaml
│   └── chapter5.yaml
├── poh/
│   ├── cruise.csv
│   ├── climb.csv
│   ├── descent.csv
│   └── metadata.yaml
└── airports/
    └── ...
```

Generated dense interpolation grids should not replace canonical source data. If cached for performance, store them as derived artifacts with reproducible generation code.

## 9. Provenance requirements

Every source-backed data set should carry:

- source title
- revision / issue / effective date where available
- page or table reference
- extraction/transcription method
- units
- applicability conditions
- notes about any transformations

Any manual correction to an extracted table must be reviewable in version control.
