# AGENTS.md

This file is the compact operating guide for coding agents working in this repository. Keep it short, stable, and focused on constraints that are hard to infer from code. Detailed domain rules live under `docs/` and should be read only when relevant to the task.

## 1. Default agent behavior

When the user asks for implementation, carry the task through **inspect → implement → validate → report**. Do not stop after analysis or a plan unless the user explicitly asked only for a plan.

Use the current task / Issue / PR as the task-specific source of truth. Treat this file as the repository-wide default. If an explicit repository-owner instruction conflicts with a default here, follow the explicit instruction. If two authoritative requirements genuinely conflict, surface the conflict instead of silently choosing one.

Prefer initiative over unnecessary clarification:

- make low-risk, reversible implementation choices yourself;
- ask only when missing information would materially change behavior, data semantics, public API, or operational correctness;
- if several independent questions are required, ask them together;
- do not ask downstream design questions before the upstream decision they depend on is resolved;
- do not repeatedly ask for confirmation once the user has already established a rule or preference.

Keep scope tight:

- solve the requested problem, including necessary tests and documentation;
- reuse existing code, libraries, helpers, and project patterns before writing new machinery;
- do not introduce abstractions, compatibility layers, frameworks, or generic infrastructure without a concrete current need;
- do not mix unrelated cleanup into the same change unless it is required for correctness;
- prefer the smallest design that remains clear and extensible for already-known requirements.

For repository changes, do not push directly to `main` unless explicitly instructed. Prefer a branch + PR. Never merge a PR unless the user explicitly asks for the merge.

Do not use sub-agents / sub-threads by default. If an independent review capability is available, it may be used for a non-trivial final review. Review should be independent from the implementation when practical. If independent review is unavailable, state that rather than pretending it occurred.

## 2. Read before changing

Before editing, inspect the relevant existing implementation and nearby tests. Also read the task's Issue / PR and the minimum relevant documentation.

Use this map instead of loading every document:

- `docs/architecture.md` — module boundaries and overall architecture.
- `docs/modeling.md` — aircraft-model assumptions and supported relationships.
- `docs/maneuver-specification.md` — maneuver semantics, targets, limits, phases, and control relationships.
- `docs/data-sources.md` — canonical source data, provenance, and interpolation data.
- `docs/traffic-patterns.md` — airport traffic-pattern / Circle / 270 geometry.
- `docs/notebook-workflow.md` — Jupyter / Docker workflow and generated artifacts.
- `docs/validation.md` — numerical and source-validation expectations.
- `docs/roadmap.md` — current project direction; not a substitute for the active task.

Search existing Issues, PRs, tests, and similar modules before designing a new solution. Reuse prior decisions after verifying that they still match the current code and task.

## 3. Source authority: preserve semantic roles

Do not use one global source priority for every question. Use the source appropriate to the role.

**Training maneuver procedure / control intent**

Use the Aviation College student training-procedure narrative and applicable general sections. These define maneuver objective, phases, targets, limits, path relationships, control relationships, and completion criteria where stated.

**Aircraft performance / limitations**

Use the applicable approved SR22 flight manual / type-certified flight manual / POH data.

**Operational / local rules**

Use the applicable Aviation College operating procedure, airport procedure, regulation, AIP-derived rule, or other explicitly supplied operational source. Do not infer local procedures from generic aviation knowledge.

**Analytical physics**

Use physics only for independently defined relationships such as coordinated-turn geometry, wind vectors, coordinate geometry, state integration, and fuel/weight bookkeeping. Physics must not overwrite source-specific operational rules.

**Calibration / real-flight data**

May refine an explicitly identified model relationship, but must not silently replace canonical source data, approved limitations, or source-backed procedures.

### Critical rule: Reference Data is advisory

Chapter-end `Reference Data` tables in the training procedures are **not** the primary maneuver definition and are **not** the aircraft-performance baseline.

Do not:

- define a maneuver solely from a Reference Data row;
- turn sparse Reference Data into an aerodynamic/performance surface;
- freeze Pitch / Power values when the narrative says to maintain another quantity and adjust inputs as required;
- silently promote Reference Data to `target`, `limit`, `control law`, or `aircraft performance`.

Reference Data may be used as `advisory_reference`, solver initialization, UI hints, sanity checks, comparison, and provenance.

## 4. Core model boundaries

Keep these concepts distinct:

- `InitialState`: initial aircraft conditions.
- `Environment`: atmosphere and wind; **weight does not belong here**.
- `FlightInput`: `Pitch`, `Bank`, `PWR`, `Flap`.
- `AircraftState`: time-varying position, heading, TAS, GS, altitude, fuel, weight, etc.
- `ManeuverSpec`: source-derived maneuver semantics.
- `ReferencePath`: desired geometric path, independent of wind.
- `Trajectory`: time-indexed simulated motion in an environment.
- `Goal` / `TerminationCondition`: completion conditions.
- `AdvisoryReference`: comparison / initialization data only.

Heading is normally state, not a continuous primary control input. `Initial HDG` and `Target HDG` are valid where the task requires them.

Current target aircraft is a Cirrus SR22 training aircraft with fixed landing gear. Do not add variable Gear state/input, routine Rudder/beta control, control-surface deflections, or full 6-DoF dynamics without an explicit requirement.

Ordinary maneuvers assume ideal coordinated flight. Forward Slip / intentional sideslip remain out of core scope unless explicitly requested.

## 5. Performance model rules

Prefer a performance-based / semi-empirical quasi-steady model before inventing aerodynamic derivatives or transient stability models.

For supported POH Chapter 5 data:

- canonical table nodes must reproduce source values;
- no extrapolation by default;
- dimensions and units must be explicit;
- canonical source values stay separate from generated dense grids;
- generated interpolation products must be reproducible;
- prefer simple multilinear interpolation unless evidence supports another method;
- combine tables only when definitions, configuration, and applicability are compatible;
- preserve provenance / coverage metadata.

A smooth interpolation surface does not prove support for every arbitrary `Pitch × Bank × PWR × Flap` transient state.

If a requested operating point cannot be justified by approved performance data, procedure narrative, analytical physics, or an explicitly documented assumption/calibration, return or raise an explicit unsupported/model-gap result. Document the missing relationship or source-domain condition that prevents support so the gap is actionable. Do not manufacture plausible-looking behavior to hide the gap.

## 6. ReferencePath, airport geometry, and NAV conventions

`ReferencePath` is desired ground geometry. Wind must not translate or deform it. Keep ReferencePath and Trajectory independently displayable.

For airport geometry:

- ARP is reference / sanity-check data only;
- runway and traffic-pattern geometry originates from the runway thresholds;
- use `RWY Center Point = midpoint(THR1, THR2)`;
- use source-backed **True Bearing** to construct runway vectors and left/right normals;
- preserve Magnetic Variation for display / checks / future use, but do not use it to place KML or ReferencePath coordinates.

For traffic-pattern identity, use **ICAO + RWY + LEFT/RIGHT traffic** as the canonical key. Do not use geographic labels such as North/South/East/West as canonical identity. If geographic orientation is useful, derive it from geometry for display only.

Unless a task explicitly narrows output, keep both LEFT and RIGHT patterns available for each runway direction. Preferred / normally used traffic side is metadata and must not delete the opposite-side geometry.

Prefer canonical airport source data under `src/sr22_course_simulator/data/airports/canonical/` instead of re-transcribing the same AIP values into airport-specific Python modules. Preserve source document / effective-date provenance when loading canonical data.

For NAV calculations:

- distinguish True vs Magnetic explicitly;
- meteorological wind direction is FROM;
- keep Reference Course / Track geometry separate from the wind-corrected Heading needed to fly it;
- reuse common vector math instead of duplicating navigation formulas.

## 7. Units and provenance

Use SI units internally unless there is a strong numerical reason not to. Aviation-facing APIs may use ft, kt, NM, fpm, degrees, and % PWR. Make conversions explicit; never mix degrees/radians or kt/m/s implicitly.

Preserve enough metadata to distinguish at least:

- `procedure_target`
- `procedure_limit`
- `procedure_nominal`
- `procedure_initial_setting`
- `advisory_reference`
- `poh_table_value`
- `poh_interpolated`
- `physics_derived`
- `calibrated`
- `assumed`
- `unsupported`

A numerically smooth result must not obscure the strength or meaning of its evidence.

## 8. Testing and validation

Every numerical feature needs deterministic tests. A plot that merely looks reasonable is not a test.

At minimum, preserve coverage for the relevant subset of:

- no-wind straight flight;
- canonical wind-vector directions;
- coordinated / constant-bank turns against analytical expectations;
- altitude propagation for known cases;
- fuel burn and weight reduction;
- exact POH table-node reproduction;
- rejection of unsupported interpolation / extrapolation;
- ReferencePath independence from wind;
- runway / traffic-pattern geometry and semantic points;
- KML coordinate and altitude ordering;
- maneuver-source transcription and semantic roles;
- source precedence: procedure narrative must not be overridden by advisory Reference Data.

After implementation:

1. run focused tests for the changed behavior;
2. run the broader test suite when practical;
3. run formatting / lint / type checks that the repository already uses;
4. run `git diff --check` when working in Git;
5. if Notebook behavior changed, execute the relevant notebook workflow when practical.

Never claim a validation passed unless it was actually run. If environment/tooling prevents a check, report the exact unverified item.

## 9. Documentation and reusable knowledge

Update docs when a change affects a model assumption, public behavior, source provenance, supported/unsupported region, or user workflow.

Record reusable knowledge when it would materially shorten or improve future work, especially:

- non-obvious design decisions and rationale;
- root causes and recurrence prevention;
- failed approaches and why they failed;
- repository-specific constraints;
- reusable implementation patterns;
- verification results that change future decisions.

Do not turn `AGENTS.md` into a work log. Raw logs, one-off observations, and facts obvious from code belong elsewhere or nowhere. Keep this file as a compact map of stable constraints.

## 10. Completion and reporting

A code task is complete only when the requested behavior is implemented, relevant tests are added/updated, validation has been run as far as the environment allows, and documentation is updated where required.

Final responses should be concise. Report:

- what changed;
- validation run and result;
- any remaining limitation / unverified item;
- PR / commit reference when applicable.

Do not dump internal reasoning or repeat the entire task specification.