-- B2.4a: immutable adaptive meal-accounting snapshots.
--
-- These rows record the remaining requirement for one meal using actual
-- consumption and actual administered meal insulin.
--
-- They are deliberately separate from the immutable version-3
-- meal_calculations plan and are NOT safe immediate insulin recommendations.
-- B2.4b-B2.4d will add accumulated active state, physiological context and
-- deterministic safety constraints.

CREATE TABLE adaptive_meal_calculations (
    id UUID PRIMARY KEY,

    patient_id UUID NOT NULL
        REFERENCES patients(id) ON DELETE CASCADE,

    meal_id UUID NOT NULL
        REFERENCES meals(id) ON DELETE CASCADE,

    calculation_id UUID NOT NULL
        REFERENCES meal_calculations(id) ON DELETE CASCADE,

    calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Actual carbohydrate consumption snapshot.
    -- NULL means complete actual meal consumption is still unknown.
    consumed_carbs_grams NUMERIC(10, 3),

    -- Immutable B2.3 effective contribution from the originating
    -- meal-calculation snapshot. This is not recalculated from current
    -- clinical settings.
    fat_protein_effective_carb_equivalent_grams NUMERIC(10, 3) NOT NULL,

    -- ICR used by this adaptive meal-accounting calculation.
    insulin_to_carb_ratio NUMERIC(10, 3) NOT NULL,

    -- Actual executed meal insulin only. Planned insulin is never included.
    actual_administered_units NUMERIC(10, 3) NOT NULL,

    -- Derived B2.4a requirements.
    -- Carb/total/remaining values stay NULL while complete actual
    -- carbohydrate consumption is unknown.
    carb_insulin_requirement_units NUMERIC(10, 3),

    fat_protein_insulin_requirement_units NUMERIC(10, 3) NOT NULL,

    total_meal_requirement_units NUMERIC(10, 3),

    remaining_meal_requirement_units NUMERIC(10, 3),

    -- Independent from calculation_version='3' and warsaw_v1.
    adaptive_calculation_version VARCHAR(50) NOT NULL,

    CONSTRAINT ck_adaptive_consumed_carbs_nonnegative
        CHECK (
            consumed_carbs_grams IS NULL
            OR consumed_carbs_grams >= 0
        ),

    CONSTRAINT ck_adaptive_fp_equivalent_nonnegative
        CHECK (
            fat_protein_effective_carb_equivalent_grams >= 0
        ),

    CONSTRAINT ck_adaptive_icr_positive
        CHECK (
            insulin_to_carb_ratio > 0
        ),

    CONSTRAINT ck_adaptive_actual_insulin_nonnegative
        CHECK (
            actual_administered_units >= 0
        ),

    CONSTRAINT ck_adaptive_carb_requirement_nonnegative
        CHECK (
            carb_insulin_requirement_units IS NULL
            OR carb_insulin_requirement_units >= 0
        ),

    CONSTRAINT ck_adaptive_fp_requirement_nonnegative
        CHECK (
            fat_protein_insulin_requirement_units >= 0
        ),

    CONSTRAINT ck_adaptive_total_requirement_nonnegative
        CHECK (
            total_meal_requirement_units IS NULL
            OR total_meal_requirement_units >= 0
        ),

    CONSTRAINT ck_adaptive_remaining_requirement_nonnegative
        CHECK (
            remaining_meal_requirement_units IS NULL
            OR remaining_meal_requirement_units >= 0
        )
);

-- Multiple immutable adaptive snapshots are intentionally allowed for the
-- same originating calculation.

CREATE INDEX ix_adaptive_meal_calculations_patient_time
    ON adaptive_meal_calculations(patient_id, calculated_at);

CREATE INDEX ix_adaptive_meal_calculations_meal_time
    ON adaptive_meal_calculations(meal_id, calculated_at);

CREATE INDEX ix_adaptive_meal_calculations_calculation_time
    ON adaptive_meal_calculations(calculation_id, calculated_at);
