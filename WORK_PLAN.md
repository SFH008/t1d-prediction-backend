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

Outstanding regression:
- Verify explicit/manual meal absorption override semantics through the calculation endpoint.

---

### B2.2 — Meal consumption + macronutrient facts
Status: IN PROGRESS

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
Status: IN PROGRESS

Component model:

- `quantity_grams` = original served/planned quantity.
- `carbs_grams` = original server-derived planned carbohydrates.
- `consumed_quantity_grams` = actual eaten quantity, nullable until known.
- `consumed_carbs_grams` = server-derived actual carbohydrates, nullable until known.

Semantic rules:

- `NULL` means consumption has not yet been recorded.
- `0` means explicitly recorded that none was eaten.
- Planned quantity/carbohydrate snapshots are never mutated.
- Client cannot provide `consumed_carbs_grams`.
- Actual carbohydrates are calculated using the component's immutable stored carb factor.
- Consumed quantity cannot exceed planned quantity.
- Multi-component updates validate completely before ORM mutation.

Completed gates:

- Consumption request schema.
- Zero consumption accepted.
- Negative consumption rejected.
- Client-supplied consumed carbs rejected.
- ORM fields nullable by default.
- Response supports unknown consumption.
- PATCH consumption path implemented.
- Server-derived consumed carbohydrates verified.
- Planned snapshots preserved.
- Over-consumption rejected.
- Multi-component validation is atomic.

Next gates:

1. Reject duplicate group numbers in a consumption update.
2. Reject components that are not part of the captured meal.
3. Verify zero-consumption persistence through endpoint.
4. Add migration `010` for:
   - `meal_carb_groups.consumed_quantity_grams`
   - `meal_carb_groups.consumed_carbs_grams`
5. Add meal-level `consumed_carbs_grams` if needed as a server-derived aggregate.
6. Define partial-update versus complete-consumption semantics explicitly.
7. Refresh/rebuild active carbohydrate timeline from actual consumed quantities.
8. Verify timeline update is atomic with consumption persistence.
9. Run full test suite.
10. Live PostgreSQL/API verification.

Dose-2 foundation:

    insulin required for actual consumed meal
    - insulin already administered
    = remaining insulin requirement

Do not implement this dose calculation until B2.2 consumption state is complete.

---

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
