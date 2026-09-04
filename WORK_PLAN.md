# T1D Prediction Backend — Work Plan

Updated: 2026-09-04

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

### B1 — Authoritative carbohydrate definitions
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

### B2.3 — Warsaw-inspired delayed nutrient model
Status: NEXT

Goals:

- Keep raw fat/protein facts separate from derived delayed nutrient contribution.
- Introduce versioned calculation snapshots.
- Do not invent clinical conversion constants.

Admin-only mode:

- `disabled`
- `advisory`
- `enabled`

Default:

- mode = disabled
- scaling percent = 0

Semantics:

- disabled: model/capture fat and protein; additional insulin = 0.
- advisory: expose delayed contribution/prediction without altering dose.
- enabled: clinician/admin-approved contribution may affect recommendation within deterministic limits.

---

### B2.4 — Adaptive split-dose engine
Status: PLANNED

Inputs:

- component absorption
- actual amount eaten
- therapy context
- Dose 1 actually administered
- admin-approved fat/protein contribution

Output:

- remaining Dose 2 recommendation

Absorption timing may change dose timing/share without increasing total carbohydrate insulin.

Fat/protein is a separate mechanism.

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

## Current implementation focus

B2.2B — actual consumption tracking.

Immediate next test:

Reject duplicate `group_number` entries in one meal-consumption request.

Do not start B2.3 until B2.2 database migration, timeline integration,
full tests, and live API verification are complete.
