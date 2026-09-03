BEGIN;

ALTER TABLE carb_group_definitions
    ADD COLUMN IF NOT EXISTS default_absorption_profile_key VARCHAR(50);

ALTER TABLE carb_group_definitions
    DROP CONSTRAINT IF EXISTS ck_carb_group_definitions_absorption_profile;

ALTER TABLE carb_group_definitions
    ADD CONSTRAINT ck_carb_group_definitions_absorption_profile
    CHECK (
        default_absorption_profile_key IS NULL
        OR default_absorption_profile_key IN (
            'very_fast',
            'fast',
            'medium',
            'slow'
        )
    );

UPDATE carb_group_definitions
SET default_absorption_profile_key = CASE group_number
    WHEN 1  THEN 'slow'
    WHEN 2  THEN 'fast'
    WHEN 3  THEN 'medium'
    WHEN 4  THEN 'medium'
    WHEN 5  THEN 'medium'
    WHEN 6  THEN 'fast'
    WHEN 7  THEN 'fast'
    WHEN 8  THEN 'slow'
    WHEN 9  THEN 'slow'
    WHEN 10 THEN 'slow'
    WHEN 11 THEN 'medium'
    ELSE default_absorption_profile_key
END
WHERE group_number BETWEEN 1 AND 11;

COMMIT;
