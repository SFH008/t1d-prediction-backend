BEGIN;

CREATE TABLE IF NOT EXISTS carb_group_definitions (
    id UUID PRIMARY KEY,
    group_number INTEGER NOT NULL UNIQUE,
    group_key VARCHAR(100) NOT NULL UNIQUE,
    group_name VARCHAR(255) NOT NULL,
    carb_factor_g_per_g NUMERIC(8,5) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_carb_group_definitions_group_number
        CHECK (group_number BETWEEN 1 AND 12),

    CONSTRAINT ck_carb_group_definitions_factor
        CHECK (
            carb_factor_g_per_g >= 0
            AND carb_factor_g_per_g <= 1
        )
);

CREATE INDEX IF NOT EXISTS
    ix_carb_group_definitions_active
ON carb_group_definitions (is_active);

INSERT INTO carb_group_definitions (
    id,
    group_number,
    group_key,
    group_name,
    carb_factor_g_per_g,
    is_active
)
VALUES
    (gen_random_uuid(), 1,  'pasta_cooked', 'Pasta, cooked', 0.28, TRUE),
    (gen_random_uuid(), 2,  'fruit',        'Fruit',         1.00, TRUE),
    (gen_random_uuid(), 3,  'vegetables',   'Vegetables',    1.00, TRUE),
    (gen_random_uuid(), 4,  'dairy',        'Dairy',         0.05, TRUE),
    (gen_random_uuid(), 5,  'snacks',       'Snacks',        1.00, TRUE),
    (gen_random_uuid(), 6,  'beverages',    'Beverages',     1.00, TRUE),
    (gen_random_uuid(), 7,  'desserts',     'Desserts',      1.00, TRUE),
    (gen_random_uuid(), 8,  'pasta_dry',    'Pasta, dry',    0.75, TRUE),
    (gen_random_uuid(), 9,  'fast_food',    'Fast food',     1.00, TRUE),
    (gen_random_uuid(), 10, 'bolognese',    'Bolognese',     0.06, TRUE),
    (gen_random_uuid(), 11, 'mixed_meal',   'Mixed meal',    1.00, TRUE)
ON CONFLICT (group_number) DO NOTHING;

COMMIT;
