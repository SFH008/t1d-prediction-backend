# T1D Prediction Backend — Work Plan

Updated: 2026-09-07

## Architecture principles

- Backend is authoritative for therapy context and insulin calculations.
- Frontend must not duplicate ICR, ISF, glucose-target, or dose logic.
- Deterministic therapy limits remain outside TensorFlow.
- TensorFlow predicts physiological response; deterministic logic converts predictions into bounded recommendations.
- Raw observations, calculation assumptions, therapy context, and model versions must remain reproducible.
- Carbohydrate insulin timing is separate from additional insulin for fat/protein.
- Fat/protein insulin contribution defaults to disabled / zero unless explicitly enabled through admin-controlled settings.

---

## Backend roadmap

### A1 — Administrative and operational control plane

Status: PLANNED / PARALLEL WORKSTREAM

Purpose:

Provide a protected administrative interface for system operation, patient
administration, clinical configuration, integrations and model lifecycle
management.

The administrative control plane is separate from the patient-facing
application and from deterministic clinical calculation logic.

Administrative interfaces call authoritative backend APIs and must not
duplicate clinical calculation logic in the frontend.

### A1.1 — Admin foundation and security

Status: PLANNED

Provide:

- dedicated desktop-first responsive admin web interface;
- authenticated administrative access;
- role/permission model;
- protected administrative API routes;
- audit trail for configuration and destructive operations;
- confirmation flows for high-risk operations;
- system/version/environment information.

Administrative roles remain separate from ordinary patient preferences.

All clinically relevant configuration changes must be attributable and
versionable.

### A1.2 — System management

Status: PLANNED

Provide system administration for:

- PostgreSQL backup;
- backup history and status;
- restore;
- database integrity checks;
- migration/schema status;
- storage/database size;
- performance and health diagnostics;
- connection/database statistics;
- maintenance operations;
- application/backend health;
- system logs and error diagnostics.

Backup and restore operations are server-controlled. Database credentials or
filesystem access must never be exposed to the browser.

Restore requires explicit confirmation and compatibility/integrity checks
before live state is replaced.

Production deployment should support scheduled automatic backups and retention
policies.

### A1.3 — Patient administration

Status: PLANNED

Provide administrative management of patient core data:

- create patient;
- view patient;
- edit patient;
- activate/deactivate patient;
- patient identifiers;
- demographic/core metadata required by the application;
- external-system identifiers;
- integration status.

Normal patient removal uses deactivation/archive semantics so historical
clinical and calculation lineage remains reproducible.

Permanent data erasure is a separate explicit administrative operation with
dependency checks, audit logging and appropriate privacy handling.

### A1.4 — Patient clinical and calculation configuration

Status: PLANNED

Provide administrative management of patient-specific clinical configuration,
including:

- insulin-to-carbohydrate ratio by time of day;
- insulin sensitivity by time of day;
- glucose targets;
- therapy limits;
- carbohydrate-group absorption configuration;
- patient-specific absorption delays;
- absorption-profile mappings;
- dose split strategy;
- Dose 2 timing parameters;
- fat/protein mode;
- fat/protein scaling;
- insulin rounding;
- future deterministic safety constraints.

Resolution remains:

    patient-specific active setting
            |
            v
    global/default setting
            |
            v
    immutable calculation snapshot

Historical calculations must never change when an administrator changes a
current setting.

Clinical configuration must be versionable and auditable.

This phase is a prerequisite for final B2.4d safe bounded recommendation
deployment.

### A1.5 — External device and data-source integrations

Status: PLANNED

Provide administrative setup and diagnostics for supported external sources,
including initially:

- Medtronic;
- future insulin-pump integrations;
- CGM integrations;
- import/API credentials;
- patient/device association;
- synchronization status;
- last successful synchronization;
- integration errors;
- enable/disable controls.

Credentials and API secrets are stored server-side and must never be returned
to the frontend after configuration.

Integration adapters remain separate from normalized internal clinical data
models.

### A1.6 — Generic model management

Status: PLANNED

Provide administration of generic/non-patient-specific model resources:

- deterministic algorithm versions;
- supported feature/model versions;
- generic TensorFlow model versions when introduced;
- model metadata;
- training/build timestamp;
- validation metrics;
- deployment status;
- active/inactive model versions;
- compatibility information;
- rollback to previously validated versions.

Generic model management remains separate from patient-specific ML state.

Patient-specific learned models are system-managed and independently
versioned.

This phase becomes operationally required with B4 model training and
promotion.

### A1.7 — Audit, diagnostics and operational maintenance

Status: PLANNED

Provide:

- administrative audit log;
- clinical-setting change history;
- integration change history;
- backup/restore history;
- model promotion/rollback history;
- application diagnostics;
- failed-job visibility;
- data-quality status;
- storage-growth indicators;
- maintenance status.

High-impact actions record actor, timestamp, operation and outcome.

The audit layer must not alter immutable historical calculation snapshots.

### Administrative dependency gates

The A1 administrative workstream runs in parallel with the B-series clinical
pipeline.

Required gates:

- B2.4b may proceed independently of the admin UI.
- B2.4c may proceed using authoritative backend clinical configuration already
  present in the database.
- B2.4d must not be considered deployment-ready until A1.4 provides controlled,
  auditable management of patient clinical/safety configuration.
- Production operation requires A1.1 and A1.2 administration/security and
  backup capability.
- B4 model promotion requires A1.6 generic model lifecycle management.
- External live-data operation should use A1.5 rather than embedding
  credentials or vendor-specific setup in patient-facing screens.

---

## B1 — Authoritative carbohydrate definitions
Status: COMPLETE

- Backend owns carb-group definitions and factors.
- Client submits group number and food quantity only.
- Backend snapshots factor, key, name, and calculated carbohydrate amount.
- Historical meal calculations remain reproducible.

Outstanding:
- Add/verify authoritative Group 12 Custom definition when custom groups are implemented.

---

### B2 — Deterministic component absorption
Status: COMPLETE

- Per-component immutable absorption snapshots.
- Patient-specific absorption profiles.
- Deterministic component curves.
- Five-minute patient-level aggregation.
- Overlapping meals sum.
- Six-hour history plus 72 future five-minute points.
- Current forecast operational state is replaceable.
- Historical forecast data remains versioned/idempotent.
- Meal capture, component snapshots, and timeline staging are atomic.

---

### B2.1 — Composition-driven absorption summary
Status: COMPLETE

Implemented:

- Single-component classification.
- Uniform multi-component classification.
- Mixed-component classification.
- Mixed meals do not receive a fabricated medium profile.
- Component-derived absorption summary persisted with explicit classification source.

Live verification completed for:

- Fruit -> fast.
- Bolognese -> slow.
- Fruit + Bolognese -> mixed.

Amendment — patient-specific per-carb-group absorption configuration:

- `carb_group_definitions.default_absorption_delay_minutes` provides the
  system/global default absorption onset delay for each carbohydrate group.
- `patient_carb_group_settings` provides optional patient-specific clinical
  overrides for absorption profile and absorption onset delay.
- Patient-specific clinical overrides are admin-managed configuration and are
  not normal user preferences.
- At meal capture, the backend resolves the active patient-specific setting
  when present; otherwise it falls back to the global carbohydrate-group
  default.
- The resolved absorption profile and delay are snapshotted into
  `meal_component_absorptions`.
- Absorption duration remains supplied by the selected patient absorption
  profile.
- Existing carbohydrate groups were migrated to a 10-minute global default,
  preserving previous behavior until deliberately configured.
- Historical meal-component snapshots remain immutable when patient or global
  configuration changes or is removed.
- Live verification confirmed a Fruit global default of 10 minutes, a temporary
  patient-specific override of 25 minutes, and a new meal snapshot of 25
  minutes with classification source `patient_carb_group_setting_v1`.
- Earlier Fruit meal snapshots remained at 10 minutes.
- The temporary patient-specific development override was removed after
  verification.
- No patient clinical-settings write API is exposed yet; authorization and
  role enforcement must be implemented before exposing that administration
  surface.
- Patient-specific TensorFlow state remains system-managed and separate from
  admin-controlled patient clinical configuration. Learned model state must
  not silently rewrite clinical settings.

Outstanding regression:
- Verify explicit/manual meal absorption override semantics through the calculation endpoint.

---

### B2.2 — Meal consumption + macronutrient facts
Status: COMPLETE

#### B2.2A — Macronutrient facts
Status: COMPLETE

Implemented:

- `Meal.fat_grams`
- `Meal.protein_grams`
- Defaults to zero.
- Negative values rejected.
- Values exposed through meal response.
- Migration `009_add_meal_macronutrients.sql`.
- Existing rows safely backfilled to zero.
- Database constraints verified.
- Full meal test module green.

Important rule:

Fat and protein stored here are nutritional facts only.
They do not alter insulin recommendations in B2.2.

#### B2.2B — Actual meal consumption
Status: COMPLETE

Implemented and verified:

- `consumed_quantity_grams` records actual eaten component quantity.
- `consumed_carbs_grams` is derived server-side from the immutable stored carb factor.
- `NULL` means consumption has not been recorded.
- `0` means explicitly recorded that none was eaten.
- Planned quantity and carbohydrate snapshots are never mutated.
- Negative consumption rejected.
- Consumption greater than planned quantity rejected.
- Client-supplied consumed carbohydrate totals rejected.
- Duplicate component numbers rejected at request validation.
- Components not belonging to the meal rejected.
- Multi-component updates validate atomically before ORM mutation.
- Zero consumption persists distinctly from unknown consumption.
- Migration `010_add_meal_consumption_fields.sql` applied.
- PostgreSQL non-negative and not-over-planned constraints verified.
- Existing component rows remain NULL/unknown after migration.
- Full backend test suite green.

Consumption aggregation rule:

- Partial component consumption updates are allowed.
- A meal-level actual carbohydrate total must not be treated as complete while
  any captured component has unknown consumption.
- Once every component has known consumption, actual meal carbohydrates can be
  derived as the sum of component `consumed_carbs_grams`.
- Do not persist a misleading partial total as `Meal.consumed_carbs_grams`.

#### B2.2C — Consumption-aware absorption timeline
Status: COMPLETE

Implemented and verified:

- Unknown consumption (`NULL`) uses planned component carbohydrate.
- Known partial consumption uses `consumed_carbs_grams`.
- Explicit zero consumption contributes zero carbohydrate.
- Planned meal/component snapshots remain unchanged.
- Consumption update flushes, rebuilds and stages the timeline, then commits once.
- Timeline rebuild failure rolls the transaction back.
- Live verification changed Bolognese consumption from unknown to explicit zero
  and reduced the operational forecast from 53.877368 g to 53.277368 g, exactly
  matching its 0.600000 g planned carbohydrate contribution.
- Full backend suite before live verification: 207 passed.


### B2.3 architecture amendment — parallel clinical model isolation

Status: LOCKED / CORRECTION COMPLETE

The project supports independent evaluation of multiple clinical calculation
models against the same immutable meal and therapy-context facts.

Model selection and exposure are authoritative backend clinical configuration.
They are controlled by administration, not by the patient-facing frontend.

The architecture distinguishes:

- one administrator-selected primary model;
- zero or more administrator-enabled alternative/comparison models;
- `warsaw_v1` is an alternative/comparison fat/protein model, not the primary
  model;
- future deterministic or TensorFlow models may also be evaluated as
  alternatives before any deliberate administrative promotion to primary.

Parallel-model invariant:

    same immutable meal + therapy-context snapshot
                    |
            +-------+-------+
            |               |
            v               v
      primary model      Warsaw v1
            |           alternative
            v               |
      primary result         v
                       Warsaw result

Each model executes independently.

Model intermediates and outputs must never be cross-fed or mathematically
blended between model branches.

In particular:

- a primary-model result must not consume a Warsaw-derived intermediate;
- a Warsaw result must not consume a primary-model intermediate;
- adaptive accounting for one model branch must use only inputs belonging to
  that model branch plus shared factual/therapy-context inputs;
- no implicit averaging, weighting, merging or selection of values from
  different model branches is permitted;
- any future calculation that intentionally combines model outputs must itself
  be an explicitly defined, independently versioned aggregation model.

Each evaluated model result must preserve sufficient provenance to identify:

- model identity;
- model version;
- role (`primary` or `alternative/comparison`);
- immutable factual input snapshot;
- immutable therapy/configuration snapshot;
- calculation version;
- calculation timestamp.

Historical model provenance is immutable. Changing the administrator-selected
primary model must affect new evaluations only and must not relabel or
reinterpret historical results.

Frontend model presentation:

- the frontend never selects or implements the clinical model;
- the backend determines the primary model and which alternative models are
  evaluated/exposed;
- the frontend clearly identifies the model that produced every displayed
  model-derived result;
- primary and alternative results may be displayed side by side;
- Warsaw must be explicitly labelled as an alternative model;
- the frontend must not combine model results or reproduce model equations.

This architecture is intentionally suitable for later side-by-side evaluation
of deterministic and patient-specific TensorFlow models. An alternative model
may be compared with actual insulin and subsequent CGM outcomes without
silently changing the configured primary clinical model.

The existing B2.3/B2.4a implementation predates this clarification and currently
allows B2.4a to consume the B2.3 Warsaw effective fat/protein contribution.
That coupling must be characterized by regression tests and removed before
B2.4b begins. Existing historical records remain historical facts and must not
be silently reinterpreted.

---

### Temporal meal workflow — Plan and Follow-up

Status: LOCKED / FRONTEND RESTRUCTURE COMPLETE

Meal planning and meal follow-up are separate temporal workflows.

A meal must not be treated as a single UI interaction because actual
consumption, actual insulin administration and deviations commonly become known
after the original plan has been created.

Conceptual timeline:

    T0  plan created
        -> immutable original meal/model calculation snapshots

    T1  meal actually starts
        -> active meal state begins

    T2  follow-up / factual update
        -> actual consumption
        -> actual insulin administration
        -> deviations
        -> independent adaptive model recalculations

    T2+n
        -> further factual updates may be appended as they become known

The observed 30–60 minute interval between planning and follow-up is a workflow
observation, not a universal clinical constant and must not be hardcoded in the
frontend.

Follow-up timing must ultimately be resolved by authoritative backend
configuration/policy and exposed to the frontend as state/timing data, for
example a future `next_follow_up_at` value. Exact API/schema naming is deferred
until that backend contract is designed.

Patient-facing frontend workflow:

    Meal Entry
        |
        v
    Current Situation
        |
        v
    Calculation
        |
        v
    MEAL PLAN
        -> original planned meal
        -> original planned dose/timing information
        -> clearly identified primary result
        -> clearly identified Warsaw alternative result
        -> no actual-consumption editing

    Home / Active Meal
        |
        v
    MEAL FOLLOW-UP
        -> original plan summary
        -> actual consumption
        -> actual insulin events
        -> deviations from plan
        -> independently recalculated primary result
        -> independently recalculated Warsaw alternative result

The Meal Plan screen answers:

    "What is the plan for this meal?"

The Meal Follow-up screen answers:

    "What actually happened, and what has changed since the original plan?"

Actual-state entry therefore belongs primarily to Meal Follow-up rather than
being appended to one long Meal Plan/Review screen.

Timestamp semantics:

- plan creation time, meal start time, actual insulin administration time and
  factual-recording time are distinct concepts;
- recording an event later must not fabricate the recording time as the actual
  administration time;
- a deliberate "given now" interaction may use current time as actual
  administration time;
- retrospective entry must preserve the real administration time when known.

This temporal separation must preserve the existing backend principle that the
original plan is immutable while subsequent actual facts and adaptive
calculations are append-only/versioned.

---

### B2.3 — Warsaw-inspired delayed nutrient model
Status: COMPLETE

Purpose:

Model delayed fat/protein contribution as explicit, versioned derived data
without changing the existing carbohydrate insulin recommendation.

Raw meal facts remain separate:

- carbohydrate grams
- fat grams
- protein grams

The B2.3 model derives:

- fat kcal = fat grams × 9
- protein kcal = protein grams × 4
- total fat/protein kcal
- fat/protein units (FPU) = total kcal / 100
- theoretical carbohydrate equivalent = total kcal / 10
- patient-scaled carbohydrate equivalent
- effective carbohydrate equivalent according to clinical mode

Patient-specific clinical configuration:

- `fat_protein_mode`
- `fat_protein_scaling_percent`

These settings belong to admin-controlled patient clinical configuration.
They are not ordinary user preferences and are not supplied by the meal
calculation client.

Supported modes:

- `disabled`
- `advisory`
- `enabled`

Default clinical configuration:

- `fat_protein_mode = disabled`
- `fat_protein_scaling_percent = 0`

Mode semantics:

- `disabled`: calculate and snapshot the model; effective contribution = 0.
- `advisory`: calculate theoretical and scaled values for evaluation;
  effective contribution = 0.
- `enabled`: scaled contribution becomes eligible for B2.4 dose-strategy
  evaluation, subject to deterministic clinical and safety constraints.

Safety boundary:

- B2.3 does not alter Dose 1 or Dose 2.
- B2.3 does not actuate insulin delivery.
- Enabled means eligible for later evaluation, not automatic insulin.
- Existing calculation-v3 `fat_protein_addon_*` semantics remain unchanged.
- Legacy fields must never be reinterpreted as Warsaw-model fields.
- Carbohydrate insulin timing remains separate from extra fat/protein insulin.

Immutable calculation snapshot:

- `fat_protein_model_mode`
- `fat_protein_model_scaling_percent`
- `fat_protein_fat_grams`
- `fat_protein_protein_grams`
- `fat_protein_fat_kcal`
- `fat_protein_protein_kcal`
- `fat_protein_total_kcal`
- `fat_protein_units`
- `fat_protein_theoretical_carb_equivalent_grams`
- `fat_protein_scaled_carb_equivalent_grams`
- `fat_protein_effective_carb_equivalent_grams`
- `fat_protein_model_version`

Current model version:

- `warsaw_v1`

Persistence:

- Patient clinical configuration is stored on `dose_strategy_settings`.
- Immutable B2.3 results are stored on `meal_calculations`.
- Migration `012_add_fat_protein_model.sql` preserves the legacy
  fat/protein add-on fields and constraints.
- Scaling is constrained to 0–100 for `warsaw_v1`.

Explicitly deferred:

- Fractional-FPU duration classification is unresolved and is not implemented.
- Warsaw duration tables are not insulin-delivery commands.
- Conversion of eligible delayed nutrient contribution into an insulin
  recommendation belongs to B2.4.
- Actual amount eaten, insulin already administered and adaptive Dose 2
  recalculation belong to B2.4.

Verification status:

- Pure B2.3 model tests pass.
- ORM persistence-contract tests pass.
- Calculation integration tests pass.
- Full backend regression: 229 tests passed.
- B2.3 completion gate accepted with the full backend regression green.
- B2.4 consumes only the immutable effective fat/protein contribution
  snapshotted by B2.3; it does not reinterpret legacy add-on fields.

---

### B2.4 — Adaptive split-dose engine
Status: CURRENT

Purpose:

Adapt the remaining meal insulin requirement as actual consumption and actual
insulin administration become known, while preserving the immutable original
version-3 meal plan.

Core invariants:

- Planned insulin is never treated as administered insulin.
- Only actual executed dose events contribute to meal insulin already given.
- `consumed_carbs_grams = NULL` means actual meal consumption is unknown.
- Explicit zero consumption is known zero.
- Planned carbohydrate must never substitute for unknown actual consumption
  in adaptive meal accounting.
- Carbohydrate insulin timing remains separate from additional fat/protein
  insulin.
- B2.4 uses the immutable B2.3
  `fat_protein_effective_carb_equivalent_grams` snapshot.
- Adaptive recalculations must not mutate the original version-3
  `meal_calculations` record.
- B2.4a is meal accounting, not yet a safe immediate insulin recommendation.
- Safe recommendation requires accumulated active state, current
  physiological context and deterministic safety constraints.

#### B2.4a — Meal remaining requirement
Status: COMPLETE

Purpose:

Calculate an immutable accounting snapshot of how much insulin the originating
meal still requires according to actual consumption, the immutable B2.3
fat/protein contribution and insulin actually administered for that meal.

Implemented and green:

- `calculate_remaining_insulin_requirement()`
  calculates actual requirement minus actual administered insulin and caps the
  remainder at zero.
- `calculate_actual_consumed_carbs()`
  preserves unknown-versus-zero consumption semantics.
- `calculate_carb_insulin_requirement()`
  converts known actual consumed carbohydrate using the immutable snapshotted
  ICR.
- `calculate_adaptive_carb_requirement()`
  composes actual consumption, ICR and actual administered insulin.
- `calculate_fat_protein_insulin_requirement()`
  converts only the immutable B2.3 effective fat/protein carbohydrate
  equivalent.
- `calculate_adaptive_meal_requirement()`
  composes carbohydrate and authorized fat/protein meal requirements.
- `calculate_actual_administered_insulin()`
  aggregates only executed `given` / `adjusted` dose events.
- `calculate_actual_consumed_carbs_from_components()`
  extracts persisted actual component consumption without falling back to
  planned carbohydrate.
- `calculate_adaptive_meal_requirement_from_state()`
  composes persisted component consumption, persisted actual dose execution,
  immutable effective fat/protein contribution and ICR.

Persistence:

- Append-only immutable adaptive snapshots are stored in
  `adaptive_meal_calculations`.
- Migration `013_add_adaptive_meal_calculations.sql` is applied and
  live-verified.
- Multiple adaptive snapshots may reference the same originating calculation.
- Every snapshot preserves patient, meal and originating-calculation lineage.
- Adaptive calculation versioning is independent from calculation-v3 and
  `warsaw_v1`.
- Current adaptive calculation version:
  `adaptive_meal_requirement_v1`.

Authoritative API boundary:

- Adaptive calculations load medical state from persisted backend data.
- The client supplies no ICR, fat/protein contribution, consumption total or
  insulin-administration total.
- The original `MealCalculation.carb_factor_g_per_unit` snapshot is reused;
  current ICR is not re-resolved.
- The original
  `MealCalculation.fat_protein_effective_carb_equivalent_grams` snapshot is
  reused; B2.3 is not recomputed using current settings.
- Current actual consumption comes only from
  `MealCarbGroup.consumed_carbs_grams`.
- Actual meal insulin comes only from executed `MealDoseEvent` state.
- Planned carbohydrate and planned insulin are deliberately excluded from the
  ORM-to-domain adaptive state boundary.
- Missing originating calculation or lineage mismatch returns not-found rather
  than exposing cross-patient/cross-meal state.
- Historical calculations missing required immutable ICR or B2.3 snapshots are
  rejected rather than treating unknown values as zero or recomputing them
  using current settings.
- Persistence failure rolls the transaction back.
- Repeated adaptive calculations append new immutable records rather than
  modifying previous snapshots.

Semantic boundary:

- `remaining_meal_requirement_units` answers how much insulin this meal still
  accounts for under the B2.4a model.
- It is not a safe immediate insulin recommendation.
- B2.4a does not account for accumulated effects from other meals or insulin
  events.
- B2.4a does not use current glucose, glucose trend, correction logic or safety
  bounds.
- B2.4a does not actuate insulin delivery.

Verification:

- Migration 013 schema, foreign keys, constraints and history indexes were
  live-verified against PostgreSQL.
- API lineage, immutable-snapshot, unknown-consumption, append-only and
  transaction rollback behavior are regression tested.
- Full backend completion gate: `311 passed, 26 warnings`.
- `git diff --check` passes.

#### B2.4b — Accumulated active state
Status: CURRENT

Aggregate overlapping historical effects at the evaluation time:

- carbohydrate on board (COB) from all relevant meal/component curves;
- remaining delayed fat/protein activity from relevant meals;
- insulin on board (IOB) from actual insulin events.

Historical effects accumulate across meals and doses. The latest meal alone is
not sufficient for a safe recommendation.

#### B2.4c — Current physiological context
Status: PLANNED

Resolve and snapshot the context required for recommendation:

- current glucose;
- glucose trend;
- ICR;
- ISF;
- glucose target;
- basal/physiological drift;
- relevant activity, hormonal and contextual features when available.

#### B2.4d — Safe bounded recommendation
Status: PLANNED

Combine:

- B2.4a meal remaining requirement;
- B2.4b accumulated active state;
- B2.4c current physiological context;
- deterministic therapy and safety constraints.

Output a separately versioned bounded recommendation.

The B2.4a `remaining_meal_requirement_units` value must not be presented as
"take this insulin now" before B2.4b, B2.4c and B2.4d are implemented.

---

### B2.5 — Longitudinal outcome/training dataset
Status: PLANNED

Capture reproducible examples from all eligible meals:

- meal composition
- actual amount eaten
- absorption snapshots
- fat/protein
- Dose 1 / Dose 2 amounts and timing
- CGM before/after
- IOB
- activity/context
- time of day
- therapy context
- outcome trajectory

No future-information leakage relative to each prediction point.

---

### B3 — Context + physiological drift features
Status: PAUSED

Prepare measurable features for:

- time of day
- glucose dynamics
- IOB
- activity
- illness/recovery where available
- longitudinal physiological drift

Do not hardcode guessed growth or hormone correction factors.

---

### B4 — Daily TensorFlow training + model promotion
Status: PAUSED

Principles:

- Train from all eligible meals.
- Patient-specific daily updates.
- Chronological train/validation/test splits.
- Immutable model versions.
- Compare candidate against deployed model.
- Never automatically promote a worse model.
- Retain model versions required to reproduce historical predictions.

---

### B5 — Personalized physiological forecasting
Status: PAUSED

TensorFlow initially predicts physiological response rather than unrestricted insulin doses.

Architecture:

    patient data
    -> TensorFlow physiological forecast
    -> deterministic therapy engine
    -> bounded recommendation

---

## F4 — Backend calculation integration and validation UI

Status: PLANNED / NEXT FRONTEND CHECKPOINT

Purpose:

Resume frontend work at defined backend milestones so deterministic clinical
state and calculation semantics are exercised through the real application
workflow rather than only through unit/API tests.

The frontend remains a presentation and interaction layer. Medical and therapy
calculations remain authoritative in the backend.

Backend tests prove mathematical behavior and invariants.
Frontend tests prove workflow and API contracts.
UI integration validates that the semantics are understandable in practice.

### F4.1 — Adaptive meal calculation API integration

Status: PLANNED

Integrate the completed B2.4a adaptive calculation endpoint into the existing
meal workflow.

The frontend must be able to:

- request a new adaptive meal-accounting snapshot;
- display actual consumed carbohydrate;
- display immutable ICR used by the adaptive calculation;
- display effective fat/protein carbohydrate equivalent;
- display carbohydrate insulin requirement;
- display fat/protein insulin requirement;
- display actual insulin already administered;
- display total meal insulin requirement;
- display remaining meal requirement;
- display calculation timestamp/version;
- preserve explicit unknown/null values.

The UI must clearly label `remaining_meal_requirement_units` as meal accounting
only.

It must not present that value as:

- "take now";
- a final Dose 2 recommendation;
- a correction recommendation;
- a pump command.

### F4.2 — Consumption / dose execution test workflow

Status: PLANNED

Provide a frontend workflow that exercises deterministic backend behavior
through realistic state transitions:

1. create meal;
2. calculate initial meal plan;
3. record actual consumption;
4. confirm, adjust or skip actual dose events;
5. request adaptive recalculation;
6. inspect the resulting immutable adaptive snapshot.

The workflow should make it easy to test:

- full meal eaten;
- partial meal eaten;
- explicit zero consumption;
- unknown consumption;
- Dose 1 given as planned;
- Dose 1 adjusted;
- planned Dose 2 not yet administered;
- skipped dose;
- repeated adaptive recalculations.

The frontend does not calculate expected clinical values itself.

Expected clinical results are derived and validated by backend tests and API
responses.

### F4.3 — Calculation diagnostics view

Status: PLANNED

Provide a development/admin-oriented diagnostics view for inspecting the
authoritative calculation chain:

    Meal
      |
      v
    original calculation-v3
      |
      v
    B2.3 fat/protein snapshot
      |
      v
    actual consumption
      |
      v
    actual executed insulin
      |
      v
    B2.4a adaptive snapshot

Show IDs, timestamps, model versions and immutable clinical snapshots where
appropriate.

This view supports development, testing and clinical-model verification and
does not need to be exposed in the normal patient workflow.

### F4.4 — Backend/frontend contract tests

Status: PLANNED

Add tests around the typed frontend API boundary for:

- response-field mapping;
- nullable/unknown values;
- Decimal/number handling;
- version fields;
- error responses;
- stale/missing historical snapshot handling;
- append-only adaptive history.

Frontend tests must not duplicate backend dose equations.

### Backend/frontend synchronization gates

The frontend must be revisited at defined backend milestones.

Required checkpoints:

- After B2.4a:
  integrate adaptive meal-accounting API and validate the end-to-end meal,
  consumption and actual-dose workflow.

- After B2.4b:
  expose accumulated COB, delayed fat/protein activity and IOB in the Home
  diagnostic graphs.

- After B2.4c:
  expose current glucose, trend and resolved therapy context used by the
  recommendation engine.

- After B2.4d:
  implement the read-only recommendation/review workflow and safety
  explanations before considering any delivery integration.

- After B2.5/B3:
  expose longitudinal outcome and feature diagnostics needed to validate
  training data.

- With B4/B5:
  expose model version, prediction horizon, confidence and comparison
  diagnostics without allowing the frontend to alter model or therapy logic.

B2.4b frontend mapping is expected to be:

    accumulated COB
        -> Active Carbohydrates graph

    accumulated IOB
        -> Active Insulin graph

    delayed fat/protein activity
        -> Active Carbohydrates delayed-nutrient series/overlay

    B2.4c glucose and trend
        -> Glucose graph and current-context display

    B2.4d bounded recommendation
        -> read-only Review/recommendation workflow

---

## Current implementation focus

B2.4a backend implementation is COMPLETE.

F4.1/F4.2 frontend integration has been implemented and runtime-validated,
including actual meal consumption, actual dose-event recording and adaptive
recalculation.

The next phase is an architecture correction checkpoint before B2.4b.

Required sequence:

1. Lock primary/alternative model isolation in backend contracts.
2. Characterize the existing B2.3/B2.4a Warsaw coupling with regression tests.
3. Separate the primary calculation branch from the `warsaw_v1` alternative
   calculation branch.
4. Preserve independent model identity, version, configuration and result
   provenance.
5. Ensure adaptive calculations remain within their originating model branch.
6. Restructure the patient frontend into separate Meal Plan and Meal Follow-up
   temporal workflows.
7. Present administrator-authorized primary and alternative model outputs
   independently and clearly identify the producing model.
8. Validate the complete Plan -> active meal -> Follow-up workflow and run full
   backend/frontend regression.
9. Only then begin B2.4b accumulated active state.

Architecture correction gate:

    same immutable facts/context
             |
       +-----+-----+
       |           |
       v           v
    PRIMARY     WARSAW v1
     MODEL      ALTERNATIVE
       |           |
       v           v
    result A     result B

There is no cross-feeding between these model branches.

Temporal workflow gate:

    T0
    Meal Plan
    immutable original plan
        |
        v
    T1
    Meal starts / active meal
        |
        v
    T2
    Meal Follow-up
    actual consumption + actual insulin
        |
        v
    independent adaptive model results

The 30–60 minute planning-to-follow-up interval is not a hardcoded clinical
constant. Backend policy/configuration will ultimately determine follow-up
timing.

After the architecture correction checkpoint, B2.4b must establish deterministic
accumulated state at an evaluation time:

- carbohydrate on board (COB) from all relevant historical meal/component
  absorption curves;
- remaining delayed nutrient/model activity from all relevant eligible meals,
  kept isolated by model provenance where model-derived;
- insulin on board (IOB) from actual insulin events.

Historical effects overlap and accumulate. No calculation may assume that the
latest meal or latest insulin dose is the only active physiological input.

B2.4b produces state, not an insulin recommendation.

The deterministic accumulated state must remain independently testable,
versionable and model-provenanced so future patient-specific TensorFlow models
can consume reproducible state without silently replacing deterministic
accounting, administrator-selected clinical models or safety logic.


---

## Architecture amendment — Patient Settings vs Back-office Administration

Status: LOCKED — 2026-09-07

The T1D Prediction system has two completely separate frontend surfaces.

### Patient application

The patient application is the Expo / React Native application.

Its Settings function is exclusively for patient-facing application
preferences, for example:

- theme and appearance;
- display preferences;
- accessibility preferences;
- notification preferences;
- other non-administrative application preferences.

The Expo application must never expose:

- clinical model enable/disable controls;
- primary/alternative model administration;
- model promotion;
- model version deployment;
- clinical algorithm configuration;
- system administration;
- administrative carbohydrate definitions;
- database/system maintenance;
- administrative integration credentials.

Administrative functionality must not be implemented as hidden Expo routes,
role-dependent Expo screens, advanced patient settings, or otherwise bundled
into the patient application.

The patient application may display results produced by models that the
authoritative backend has decided to expose, but it cannot enable, disable,
configure, promote or administer those models.


### Back-office administration

Clinical, system and model administration is provided through a separate
back-office web application.

The back-office web application:

- is not part of the Expo / React Native patient frontend;
- is not exposed to patients;
- uses protected backend `/admin/...` APIs;
- is intended for authorized administrative users;
- manages system, clinical and model configuration;
- must not duplicate clinical calculation logic in browser code.

Backend authorization is the security boundary. Merely hiding the
administrative webpage is not sufficient security.

Conceptual application separation:

    t1d-prediction-frontend
        Patient Expo / React Native application

    t1d-prediction-admin
        Separate back-office web application

    t1d-prediction-backend
        Authoritative FastAPI APIs and PostgreSQL persistence

    t1d-prediction-model
        Model/training implementation


### Settings ownership

Three different settings domains must remain distinct:

    Patient / Expo application settings
        UI, appearance, notifications and user-facing preferences

    Patient-specific clinical settings
        ICR, ISF, therapy profiles, dose strategies and other
        authoritative clinical parameters

    System-admin model settings
        Primary model identity
        Alternative model enablement/exposure
        Model versions
        Future validated model promotion and rollback

`UserSettings` must not become the authority for enabling clinical calculation
models.

Clinical/model enablement belongs to the administrative control plane.


---

### A1.6 amendment — Model administration vertical slice

Status: COMPLETE — 2026-09-07

The first functional back-office vertical slice will be model management.

Purpose:

Provide the authoritative configuration required by adaptive model
orchestration before the parallel model API is completed.

Initial supported models:

    Primary v1
        role: PRIMARY
        execution/exposure: always active

    Warsaw v1
        role: ALTERNATIVE
        execution/exposure: controlled by backend admin configuration

Warsaw must never be enabled merely because a historical meal calculation
contains Warsaw snapshot fields.

Whether Warsaw is executed and exposed for a new parallel orchestration
request is determined by the authoritative current backend-admin model
configuration.

The historical Warsaw calculation inputs remain immutable snapshots and are
used when Warsaw is executed so historical calculation lineage remains
reproducible.

The initial model-management persistence/API should represent the model
concept rather than introducing a special-purpose `enable_warsaw` application
setting.

Minimum model administration contract:

- model identity;
- model version;
- model role (`primary` or `alternative`);
- enabled/exposed state;
- administrative update timestamp/provenance;
- future-compatible versioning/audit path.

Do not build a complete ML deployment platform at this checkpoint.

The purpose of this vertical slice is to establish the authoritative control
plane that B2.4a.3 requires.


### Back-office model management test UI

A minimal separate back-office webpage will be implemented as part of this
vertical slice.

It is explicitly NOT implemented in the Expo repository.

Initial functional requirement:

    Warsaw OFF
        -> backend admin configuration persists OFF
        -> adaptive model orchestration executes Primary only
        -> response:
             primary = primary_v1
             alternatives = []

    Warsaw ON
        -> backend admin configuration persists ON
        -> adaptive model orchestration executes Primary independently
        -> adaptive model orchestration executes Warsaw independently
        -> response:
             primary = primary_v1
             alternatives = [warsaw_v1]

The test must exercise the full vertical path:

    Back-office web toggle
        ->
    protected admin API
        ->
    PostgreSQL model configuration
        ->
    adaptive-model orchestrator
        ->
    returned Primary / alternative model set

Turning an alternative model OFF affects future orchestration only.

It must never delete, relabel or invalidate historical model calculation
snapshots.


---

### B2.4a.3 — Parallel adaptive model exposure

Status: COMPLETE — 2026-09-07

Parallel exposure is orchestration, not a third clinical model.

The orchestration endpoint consumes one authoritative persisted meal state
and independently executes the models authorized by backend administration.

Required behavior:

    load originating calculation once
    load actual component consumption once
    load actual insulin events once

                    same factual state
                           |
              +------------+------------+
              |                         |
              v                         v
          Primary v1            enabled alternatives
              |                         |
              v                         v
       independent result       independent result
              |                         |
              +------------+------------+
                           |
                    one transaction
                           |
                           v
                   presentation response

Primary v1 is always evaluated.

Warsaw v1 is evaluated and exposed only when the authoritative backend-admin
model configuration says Warsaw is enabled.

The frontend contract remains generic:

    {
        "primary": <AdaptiveMealCalculationResponse>,
        "alternatives": [
            <AdaptiveMealCalculationResponse>,
            ...
        ]
    }

The API must not contain a permanent structural `warsaw` response field.

No model may consume another model's intermediate values or outputs.

The orchestrator must not implement parallel execution by sequentially
calling the existing Primary and Warsaw HTTP route handlers.

It must:

- load authoritative state once;
- call each model service independently;
- create separately versioned calculation snapshots;
- persist all results in one transaction;
- expose only admin-authorized alternatives.

Existing individual Primary and Warsaw endpoints remain available for
testing, diagnostics and explicit model execution.

Implementation verification — 2026-09-07:

- Parallel endpoint:
  `POST /patients/{patient_id}/meals/{meal_id}/calculations/{calculation_id}/adaptive/models`.
- The originating calculation, actual component consumption and actual insulin
  events are each loaded once for the orchestration request.
- Enabled clinical-model configuration is loaded from the administrative
  control plane.
- Primary and Warsaw calculations call their existing independent domain
  services; the orchestrator does not call one HTTP route handler from another.
- Primary and alternative snapshots are separately model-versioned.
- Warsaw disabled produces `alternatives = []` and does not require a Warsaw
  historical snapshot.
- Warsaw enabled produces an independent `warsaw_v1` alternative and requires
  its immutable Warsaw input snapshot.
- All generated snapshots are persisted in one transaction.
- Commit failure rolls the complete orchestration transaction back.
- Full backend regression gate: `346 passed, 28 warnings in 1.98 s`.


---

## Current implementation focus — 2026-09-09

The architecture-correction and Meal Flow checkpoint is complete.

Completed baseline:

    B2.4a.1 Primary adaptive isolation
        COMPLETE

    B2.4a.2 Warsaw adaptive isolation
        COMPLETE

    Adaptive persistence / provenance isolation
        COMPLETE

    A1.6 Model administration vertical slice
        COMPLETE
        - generic model configuration persisted in PostgreSQL
        - `/admin/clinical-models` management API implemented
        - separate React/TypeScript/Vite back-office application implemented
        - browser Warsaw ON/OFF persistence verified
        - Primary and alternative administration remain separate from
          the patient application

    B2.4a.3 Parallel model exposure
        COMPLETE
        - Primary always executes
        - authoritative admin model configuration is consulted
        - Warsaw executes/exposes only when enabled
        - generic `alternatives[]` response contract
        - one authoritative factual-state load
        - independent Primary/Warsaw calculations
        - one persistence transaction
        - model provenance remains isolated

    Patient Expo model-result integration
        COMPLETE
        - `/adaptive/models` is the patient-app adaptive calculation contract
        - Primary and backend-authorized alternatives are presented independently
        - patient Expo contains no clinical model administration controls

    Temporal Meal Flow
        COMPLETE
        - immutable captured Meal Plan
        - explicit Meal started transition
        - backend-authoritative active meal
        - actual component consumption recording
        - actual dose-event given / adjusted / skipped recording
        - automatic completion when all consumption is known and all planned
          dose events are terminal
        - Recording complete confirmation prevents repeated submission
        - completed meal remains available to Adaptive Meal Accounting
        - Home refresh removes stale active-meal presentation
        - Return Home permits capture of the next meal
        - meal completion means recording/workflow completion, not
          physiological inactivity

    Tablet patient frontend foundation
        COMPLETE FOR CURRENT UX
        - phone layout preserved
        - tablet portrait responsive composition
        - tablet landscape/wide responsive composition
        - responsive carb-group column counts
        - shared Expo application, API contracts and meal-domain logic
        - further visual refinement is deferred until justified by runtime UX

Parked non-blocking validation:

    Warsaw v1 non-zero fat/protein runtime validation
        PARKED pending patient clarification
        - current zero-value runtime observations are consistent with meals
          containing zero fat/protein and disabled/zero-scaling Warsaw settings
        - no clinical configuration will be invented merely to force a
          non-zero validation result
        - this validation no longer blocks B2.4b
        - Primary/Warsaw model isolation remains a hard invariant

Current phase:

    B2.4b — Accumulated active state
        CURRENT / UNBLOCKED

    B2.4b.0 — Insulin Model & IOB Architecture Audit
        CURRENT

B2.4b must establish deterministic accumulated physiological state at an
evaluation time from all relevant historical actual events:

    actual insulin events
        -> insulin on board (IOB)

    actual consumed carbohydrate + component absorption curves
        -> carbohydrate on board (COB)

    eligible delayed nutrient/model activity
        -> separately model-provenanced delayed activity

Historical effects overlap and accumulate. The latest meal or latest insulin
event alone is never sufficient.

B2.4b produces physiological/accounting state, not an insulin recommendation.

The accumulated-state implementation must be:

- deterministic;
- independently testable;
- versioned;
- reproducible for an explicit evaluation timestamp;
- based on actual historical events rather than planned insulin;
- capable of accumulating overlapping meals and insulin events;
- model-provenanced where model-derived state is involved;
- strictly isolated between Primary and Warsaw alternative-model branches;
- suitable as deterministic input to later TensorFlow/Keras forecasting.

The Expo Settings function remains part of the patient application, but is
limited to patient-facing application preferences such as theme, appearance,
notifications and related UI preferences.

It is not an administrative surface.
