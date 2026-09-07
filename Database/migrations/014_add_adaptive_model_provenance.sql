-- B2.4a model-isolation/provenance correction.
--
-- Migration 013 created the original append-only adaptive accounting
-- table while B2.4a still treated the Warsaw fat/protein result as part
-- of every adaptive snapshot.
--
-- Primary and Warsaw are now independent model branches. Warsaw-specific
-- values therefore become nullable:
--
--   NULL = the Warsaw field does not apply to the model
--   0    = the Warsaw model evaluated the field and produced zero
--
-- Existing historical rows are preserved.

ALTER TABLE adaptive_meal_calculations
    ADD COLUMN adaptive_model_version VARCHAR(50);

-- Rows created before explicit model provenance used the Warsaw-derived
-- fat/protein fields as part of adaptive accounting. Preserve that
-- historical provenance rather than relabelling them as primary.
UPDATE adaptive_meal_calculations
SET adaptive_model_version = 'warsaw_v1'
WHERE adaptive_model_version IS NULL;

ALTER TABLE adaptive_meal_calculations
    ALTER COLUMN adaptive_model_version SET NOT NULL;

ALTER TABLE adaptive_meal_calculations
    ALTER COLUMN fat_protein_effective_carb_equivalent_grams DROP NOT NULL;

ALTER TABLE adaptive_meal_calculations
    ALTER COLUMN fat_protein_insulin_requirement_units DROP NOT NULL;
