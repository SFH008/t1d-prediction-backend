T1D Prediction Backend --- Deterministic Physiological Model Design

Status: Locked architecture reference
Date: 2026-09-09
Scope: Deterministic COB/IOB physiological state, live Medtronic
integration, patient-specific model selection, and boundary to future
probabilistic models.

1. Purpose

This document defines the terminology and architecture for the
deterministic physiological model layer of the T1D Prediction App.

The system separates:

Factual observations and delivered events

Deterministic physiological models

Patient-specific model configuration

Deterministic physiological state at an explicit evaluation time

Future probabilistic TensorFlow/Keras models

The deterministic layer must remain reproducible, independently
testable, versioned, patient configurable, and usable both for live
operation and retrospective model training.

2. Core terminology

2.1 CGM

Continuous Glucose Monitoring data is a factual observation stream.

CGM tells us what happened to glucose. It is not an IOB or COB model.

Typical facts include:

sensor glucose

observation timestamp

sensor state

glucose trend

device/source provenance

The Medtronic/arm sensor normally provides new glucose observations
approximately every five minutes.

2.2 COB --- Carbohydrates on Board

COB represents carbohydrate that has been consumed but whose modeled
physiological absorption/effect is not yet complete.

The existing component-level carbohydrate absorption implementation is
the foundation of the deterministic COB model.

COB must be calculated from actual consumption, never merely planned
consumption.

It must support:

component-specific carbohydrate quantities

absorption delay

absorption duration

overlapping meal components

overlapping historical meals

explicit evaluation time

completed meals whose carbohydrate physiology remains active

Meal workflow completion does not imply COB is zero.

2.3 Warsaw / delayed nutrient model

Warsaw is an alternative deterministic model for delayed
fat/protein-derived carbohydrate-equivalent activity.

Warsaw remains model-isolated from the primary carbohydrate absorption
model.

It may contribute to the broader deterministic nutrient-on-board state,
but Warsaw-specific intermediate values and provenance must not be
silently mixed into the Primary model.

The Warsaw non-zero fat/protein runtime validation remains to be
completed.

2.4 IOB --- Insulin on Board

IOB represents delivered insulin that remains physiologically active at
an explicit evaluation time.

IOB is a deterministic model family, not one universal equation.

Different IOB implementations may differ in two independent dimensions:

Insulin accounting/inclusion policy

which delivered insulin events contribute to the model

Insulin action kernel

how the remaining activity of an included insulin event changes
over time

Examples of action kernels may include linear, curvilinear, and future
pharmacokinetic/pharmacodynamic models.

A correction-only accounting policy and a curvilinear action kernel are
therefore different concepts and must be modeled independently.

2.5 Probabilistic models

TensorFlow/Keras/LSTM models belong to a later probabilistic layer.

They may consume deterministic COB, IOB, nutrient activity, glucose
history, and patient context as features.

They do not redefine the deterministic facts or deterministic model
outputs.

3. Fundamental architecture

                 LIVE / HISTORICAL FACTS
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
       CGM          INSULIN EVENTS      MEALS
                         |                |
                         |                v
                         |             COB MODELS
                         |          + Warsaw branch
                         v
                     IOB MODELS
                         |
        +----------------+----------------+
                         |
                         v
             DETERMINISTIC PATIENT STATE
                  at evaluation time T
                         |
                         +--> operational UI/state
                         |
                         +--> deterministic logic
                         |
                         +--> future TensorFlow/Keras
                              probabilistic forecasting

4. Facts are separate from models

The Medtronic feed is a factual source. It is not itself a physiological
model.

Medtronic / app / other source
             |
             v
       normalized facts
             |
      +------+------+
      |             |
      v             v
   COB models    IOB models

This separation allows future pump or CGM providers to be introduced
without changing the physiological model contracts.

5. Live Medtronic integration

The architecture assumes a live Medtronic interface that refreshes
approximately every five minutes.

The interface may provide:

CGM observations

automated basal micro-delivery

automated correction boluses

recommended/manual boluses

pump delivery/suspension state

meal/carbohydrate markers

device state

Medtronic-reported active insulin

Every ingestion cycle must be idempotent.

receive Medtronic update
        |
        v
normalize source records
        |
        v
deduplicate source events
        |
        v
persist factual observations/events
        |
        v
evaluate deterministic state at T
        |
        v
forecast / UI / historical state

5.1 Event time versus ingestion time

The system must distinguish:

event/observation timestamp --- when glucose was measured or
insulin was delivered

received/recorded timestamp --- when our backend received or
persisted the record

Physiological models use event time.

Late-arriving data must therefore be capable of causing historical
deterministic state to be rebuilt.

5.2 Explicit evaluation time

Deterministic model functions must accept an explicit evaluation_time.

They must not depend implicitly on now().

The five-minute feed determines the normal live evaluation cadence, but
the models themselves must work at arbitrary timestamps.

This supports:

historical reconstruction

delayed device data

model comparison

reproducible tests

leakage-safe training datasets

retrospective validation

6. Insulin factual ledger

IOB is calculated from the complete factual insulin ledger, not from
meal dose events alone.

Actual insulin may originate from:

manual meal bolus

manual correction

recommended bolus

automated correction

automated basal delivery

other supported pump delivery

imported historical pump data

other verified delivery sources

6.1 Delivered insulin invariant

Manual delivered insulin      -> factual insulin
Automated delivered insulin   -> factual insulin

Planned insulin               -> NOT delivered insulin
Recommended but not delivered -> NOT delivered insulin
Cancelled delivery            -> NOT delivered insulin
Failed delivery               -> NOT delivered insulin

Only successfully delivered insulin may enter an IOB model.

6.2 Preserve independent insulin dimensions

Do not collapse insulin semantics into one overloaded insulin_type.

Preserve independent dimensions such as:

delivery class
    basal
    bolus
    other

administration / activation origin
    automated
    recommended
    manual
    imported
    unknown

purpose
    meal
    correction
    basal
    combined
    unknown

source
    medtronic_live
    medtronic_import
    app
    other

Source-native semantics should also be retained where practical.

For Medtronic this includes values such as:

AUTO_BASAL_DELIVERY

AUTOCORRECTION

RECOMMENDED

programmed amount

delivered amount

completion status

The normalized representation must not discard useful source provenance.

7. Medtronic insulin semantics

The raw interface demonstrates distinct insulin delivery forms.

Automated basal

AUTO_BASAL_DELIVERY represents automated pump insulin micro-delivery.

This is actual delivered insulin and belongs in the factual insulin
ledger.

Automated correction

An insulin event with activationType = AUTOCORRECTION represents
automated correction insulin.

It is distinct from automated basal delivery but is still actual
delivered insulin.

Recommended insulin

activationType = RECOMMENDED must initially be preserved as source
provenance.

The backend must not automatically equate RECOMMENDED with manual
until that Medtronic semantic has been explicitly established.

Programmed versus delivered amount

Where both are supplied:

programmed amount describes intended pump delivery

delivered amount describes actual delivery

IOB uses actual delivered insulin.

8. Medtronic-reported active insulin

The Medtronic interface may provide its own activeInsulin value.

This value is useful as a reference signal but must not become the input
to our own deterministic IOB calculations.

actual delivered insulin ledger
        |
        +--> our IOB model A
        +--> our IOB model B
        +--> our IOB model C

Medtronic activeInsulin
        |
        +--> external comparison / validation reference

This allows us to compare our deterministic models against both:

Medtronic-reported active insulin

subsequent observed CGM behavior

9. IOB model framework

IOB models must be registered model specifications rather than
hard-coded behavior inside API routes.

Conceptually:

IOB MODEL SPECIFICATION
|
+-- identity
|     model_key
|     model_version
|
+-- accounting policy
|     included insulin classes/purposes
|     basal handling
|     correction handling
|
+-- action kernel
|     linear
|     curvilinear
|     future PK/PD
|
+-- parameters
|     action duration
|     onset if applicable
|     peak if applicable
|     model-specific parameters
|
+-- provenance/version

A deterministic IOB calculation at time T is conceptually:

actual InsulinEvent ledger
          |
          v
 selected accounting policy
          |
          v
 selected action kernel
          |
          v
 remaining contribution of each event at T
          |
          v
         SUM
          |
          v
        IOB(T)

10. COB model framework

The existing component absorption engine should be reused as the Primary
COB foundation rather than replaced.

The COB engine must accumulate relevant actual carbohydrate from all
historical components/meals that remain physiologically active at
evaluation time.

Conceptually:

actual consumed meal components
           |
           v
 immutable absorption parameters
           |
           v
 component absorption curves
           |
           v
 overlap/aggregate at T
           |
           v
          COB(T)

The precise COB semantics during a component's pre-absorption delay must
be explicitly tested and locked when the accumulated COB implementation
is completed.

11. Warsaw model boundary

Warsaw is a deterministic alternative/delayed nutrient model.

Hard invariants:

Warsaw must not:
    create a dose event
    change dose_number
    replace planned_units
    select confirm/adjust/skip target
    write an insulin event
    alter Primary model intermediates

Warsaw results retain their own model/version provenance.

The broader patient physiological state may expose Warsaw/delayed
nutrient activity alongside Primary COB, but the models remain
independently identifiable.

12. Patient-specific deterministic models

Each patient must be able to have personalized deterministic model
configuration.

There are three levels of control.

12.1 System model registry

The backend owns a registry of supported deterministic models.

Examples:

COB:
    component_absorption_v1
    warsaw_v1

IOB:
    iob_linear_total_v1
    iob_curvilinear_total_v1
    future models...

Models are versioned and can be enabled or disabled administratively.

12.2 Admin authorization

The admin module controls:

models enabled globally

models authorized for a patient

patient-specific model parameters

whether patient selection is allowed

optionally a model locked by an administrator

Example selection modes:

admin_locked
patient_selectable

12.3 Patient selection

A patient may select a personalized primary model only from models
authorized by the backend for that patient.

The patient application must not activate arbitrary algorithms or submit
arbitrary model identifiers.

Conceptually:

system registry
      |
      v
admin enables model
      |
      v
admin authorizes model for patient
      |
      v
patient chooses from authorized models
      |
      v
backend validates selection
      |
      v
patient active model

13. Patient model profile

A future patient deterministic-model profile should conceptually
contain:

COB
    selected primary model
    patient absorption parameters
    authorized alternatives

Warsaw
    enabled/authorized state
    Warsaw parameters
    model version

IOB
    selected primary model
    authorized alternatives
    accounting policy
    action kernel
    action duration
    onset/peak parameters where applicable

selection controls
    admin_locked / patient_selectable

The exact database schema is to be designed from this contract rather
than inferred from current tables.

14. Immutable model provenance

Changing patient model settings must not make an old calculation
impossible to reproduce.

Every persisted deterministic evaluation that requires historical
reproducibility should retain sufficient provenance, including as
appropriate:

patient_id
evaluation_time

model_family
model_key
model_version
model_role

parameter snapshot

input/event provenance

calculated state
calculation version

Patient settings are therefore resolved for an evaluation and
snapshotted where required.

15. Deterministic patient state

At an explicit evaluation timestamp T, the deterministic state may
contain:

evaluation_time

CGM factual state
    glucose
    trend
    source freshness

COB state
    primary COB
    model/version
    provenance

delayed nutrient state
    Warsaw or other authorized model state
    model/version
    provenance

IOB state
    selected IOB
    model/version
    parameters
    provenance

COB, Warsaw, and IOB remain separately identifiable even when presented
through one patient-state object.

16. Five-minute operational timeline

The normal live cadence is driven by Medtronic/CGM updates.

CGM       o----o----o----o----o----o
           |    |    |    |    |
Pump       o-o--o----o-o--o----o---
           |
Meals      ------o------------------
                  |
                  v
       deterministic state at T
          glucose(T)
          COB(T)
          Warsaw activity(T)
          IOB(T)

The individual factual streams need not have exactly matching
timestamps.

The state engine aligns them by explicit evaluation time and historical
event timestamps.

17. CGM and deterministic model validation

CGM is the observed outcome stream against which deterministic model
behavior can later be evaluated.

This allows several deterministic models to be calculated in parallel
during research/validation:

actual CGM trajectory
          |
   +------+------+------+
   |      |      |      |
 IOB A  IOB B  IOB C  ...

The same principle applies to alternative COB/nutrient models.

A patient's preferred deterministic model may later be informed by
retrospective performance, but model selection and parameter changes
remain explicit and versioned.

18. Boundary to probabilistic models

Probabilistic models are built only after the deterministic
physiological layer is stable.

At training/evaluation time T, a leakage-safe feature row may include
facts known at or before T:

evaluation_time

current glucose
recent glucose history
glucose trend

selected COB state
selected Warsaw/delayed nutrient state
selected IOB state

actual historical insulin
actual historical carbohydrate

patient context
time-of-day context
other known variables

Targets are future observations, for example:

glucose at T + 5 min
glucose at T + 10 min
...
glucose at T + forecast horizon

The probabilistic model learns the relationship between deterministic
physiological state, patient context, and subsequent CGM behavior.

19. Core invariants

The following are architectural hard gates.

planned food    != actual food
planned insulin != actual insulin

meal lifecycle  != physiological activity

CGM observation != COB model
CGM observation != IOB model

Medtronic feed  != physiological model

COB             != IOB
Primary COB     != Warsaw
deterministic   != probabilistic

manual delivery    and automated delivery
are both factual delivered insulin when successful

planned/recommended insulin is not delivered insulin
until actual delivery is confirmed

IOB uses actual delivered insulin only

COB uses actual consumed carbohydrate only

completed meal does not mean COB is zero

all deterministic models use explicit evaluation time

patient model selection is backend-authorized

model identity, version and parameters must be reproducible

20. B2.4 deterministic roadmap

The terminology above supersedes the earlier vague use of "accumulated
active state."

B2.4b --- Deterministic COB and IOB State

B2.4b.1 --- Complete deterministic COB state

accumulate actual consumed carbohydrate across historical
meals/components

reuse existing absorption curves

support overlapping absorption

define pre-absorption-delay COB semantics

preserve completed-meal physiological activity

complete Warsaw delayed nutrient runtime validation

retain Primary/Warsaw model isolation

B2.4b.2 --- Deterministic IOB model framework

model registry

accounting-policy contract

action-kernel contract

explicit evaluation time

patient-specific parameter contract

actual-delivery-only invariant

manual/automated/source provenance

B2.4b.3 --- First deterministic IOB reference models

implement and test agreed reference action kernels

initially include linear and curvilinear models as appropriate

keep accounting policy independent from action kernel

compare models at identical evaluation timestamps

preserve Medtronic activeInsulin as an external reference

B2.4b.4 --- Patient-specific deterministic model configuration

backend model registry

admin global enable/disable

per-patient authorization

patient-selectable versus admin-locked configuration

patient-selected primary model

patient-specific model parameters

immutable/versioned provenance

B2.4b.5 --- Combined deterministic patient state at time T

current CGM factual state

COB

Warsaw/delayed nutrient state

IOB

model/version/parameter provenance

source freshness

historical reconstruction support

five-minute live evaluation support

Later phase --- Probabilistic models

Only after deterministic state is established:

TensorFlow/Keras/LSTM forecasting

personalized probabilistic models

deterministic-state feature integration

future glucose prediction

confidence/uncertainty estimates

retrospective model comparison and personalization

21. Locked design statement

CGM tells us what happened to glucose. COB models what consumed
carbohydrate remains physiologically active. IOB models what actually
delivered insulin remains physiologically active. Warsaw is an isolated
deterministic delayed nutrient model. All deterministic models are
evaluated at an explicit timestamp, normally refreshed from the live
Medtronic data stream approximately every five minutes. Patient-specific
model availability and parameters are controlled by the backend/admin
layer, while patients may select a personalized model from models
explicitly authorized for them. Probabilistic TensorFlow/Keras models
are a later layer that consumes these deterministic states and observed
history rather than replacing them.

22. Reference platform — Medtronic MiniMed 780G SmartGuard (AID)

The primary platform around which the first deterministic implementation is designed is the Medtronic MiniMed 780G with SmartGuard automated insulin delivery (AID).

This is a reference platform profile, not a hard coupling of the physiological engine to Medtronic. The generic model registry and factual event ledger remain provider-neutral.

22.1 SmartGuard operating characteristics

The reference profile assumes:

platform:
    Medtronic MiniMed 780G

automation:
    SmartGuard AID

control cadence:
    approximately every 5 minutes

automated delivery:
    adaptive Auto Basal
    automatic correction boluses / micro-corrections

meal handling:
    meal bolus / Bolus Wizard / SmartGuard bolus

relevant patient settings:
    insulin-to-carbohydrate ratio (ICR)
    Active Insulin Time (AIT)
    SmartGuard glucose target

The live interface demonstrates separate factual records for automated basal micro-delivery, automated correction insulin, recommended bolus insulin, meals, CGM, and the pump's own active-insulin estimate.

22.2 Active Insulin Time

For SmartGuard, AIT is treated as an algorithm parameter, not as a literal statement of the physiological lifetime of rapid-acting insulin.

The initial SmartGuard reference profile should support the documented 2–4 hour configurable range and especially the clinically common/recommended 2–3 hour region.

The deterministic model registry must therefore treat AIT as an explicit, patient-specific, versioned model parameter.

Conceptually:

iob model configuration
    |
    +-- action kernel / curve
    |
    +-- AIT
    |      2 h
    |      2.25 h
    |      ...
    |      4 h
    |
    +-- accounting policy
    |
    +-- model version

A shorter configured AIT produces less modeled bolus insulin remaining sooner and allows correction logic to act more aggressively. A longer configured AIT carries modeled bolus insulin for longer and therefore tends to make correction behavior more conservative.

The initial educational/model-comparison focus should include the 2–3 hour range, while retaining the complete supported configuration range.

Older pre-AID Bolus Wizard practices involving much longer AIT settings are not part of the SmartGuard reference model and must not be mixed into the 780G AID implementation.

22.3 Curvilinear IOB reference behavior

The 780G/Bolus Wizard/SmartGuard reference should be modeled with a curvilinear remaining-insulin profile, while acknowledging that the manufacturer's exact curve and complete SmartGuard control logic are proprietary.

Therefore:

Medtronic-compatible reference IOB
    != exact proprietary SmartGuard implementation

Our implementation must have its own:

documented curve specification

deterministic equations

unit tests

model key

model version

patient-specific AIT snapshot

reproducible output

The system may compare that output with Medtronic-reported activeInsulin, but must not claim exact equivalence to the proprietary SmartGuard algorithm unless independently validated.

22.4 Pump-displayed active insulin versus total delivered insulin

This distinction is mandatory.

Medtronic documents the pump's displayed active-insulin amount as representing active bolus insulin. Auto Basal/Safe Basal delivery is not included in that displayed amount.

Our factual insulin ledger, however, must retain all actual delivered insulin, including:

manual/recommended bolus
automated correction bolus
automated basal micro-delivery
other verified delivered insulin

We must therefore support at least two distinct concepts:

A. 780G-style bolus IOB reference
   - based on delivered bolus insulin according to the model's
     explicit accounting rules
   - useful for comparison with pump-reported activeInsulin

B. total deterministic insulin state
   - built from the complete delivered-insulin ledger
   - includes automated basal delivery when the selected model
     explicitly defines how basal delivery contributes

These values must never be silently conflated.

22.5 Accounting policy remains independent from action curve

The 780G reference reinforces the design decision that accounting policy and action kernel are separate model dimensions.

For example:

model:
    iob_780g_reference_v1

action kernel:
    curvilinear

AIT:
    patient-specific, within supported SmartGuard range

accounting view:
    bolus IOB reference

included bolus delivery:
    meal/recommended bolus
    correction bolus
    automated correction bolus

basal handling:
    excluded from pump-comparable displayed-bolus-IOB view
    retained in total delivered-insulin ledger

A separate deterministic model may calculate broader total insulin activity from the same factual ledger without changing or corrupting the 780G-compatible bolus IOB result.

22.6 SmartGuard factual streams

The live 780G feed should normalize, preserve, and deduplicate:

CGM:
    sensor glucose
    timestamp
    trend
    sensor/device state

AUTO_BASAL_DELIVERY:
    timestamp
    delivered amount
    source-native marker

INSULIN / AUTOCORRECTION:
    timestamp
    programmed amount
    delivered amount
    completion status
    activation type

INSULIN / RECOMMENDED:
    timestamp
    programmed amount
    delivered amount
    completion status
    activation type

MEAL:
    timestamp
    carbohydrate grams

PUMP STATE:
    SmartGuard / manual mode
    suspension state
    reservoir
    communication state
    relevant configuration

ACTIVE INSULIN:
    pump-reported reference value
    timestamp

Source-native Medtronic semantics must be retained alongside our normalized representation.

22.7 Platform lock

For the first deterministic IOB implementation, the development target is:

PRIMARY REFERENCE PLATFORM
    Medtronic MiniMed 780G SmartGuard

PRIMARY REFERENCE IOB FAMILY
    curvilinear bolus IOB
    patient-specific AIT
    780G-compatible accounting semantics
    explicit model/version provenance

SECONDARY / COMPARISON MODELS
    linear IOB
    other curvilinear models
    future PK/PD models

TOTAL INSULIN STATE
    separate from pump-displayed bolus IOB
    derived from complete actual-delivery ledger
    model-defined basal handling

The provider-neutral deterministic framework remains the architectural foundation, but the 780G SmartGuard is the concrete platform against which the initial implementation, live ingestion, model comparison, and validation are designed.