-- PostgreSQL 16 schema bootstrap — Smart Campus Digital Twin
--
-- NOTE: postgres:16-alpine does NOT support POSTGRES_MULTIPLE_DATABASES (Bitnami only).
-- We create the Airflow database here explicitly so Airflow can start.
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec

-- Keycloak uses its own database (configured via env/keycloak.env).
SELECT 'CREATE DATABASE keycloak'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec

-- PostgreSQL 16 schema bootstrap — Smart Campus Digital Twin
--
-- Responsibilities:
--   * Building / room metadata (referenced by all services as a lookup table)
--   * Daily energy summaries   (written by Spark DailyEnergyReportJob via Airflow)
--   * Anomaly audit log        (written by Flink AnomalyJob via JDBC sink)
--   * Weekly ML feature store  (written by Spark WeeklyMLFeaturesJob via Airflow)
--   * Alert rules              (read by Flink AnomalyJob to configure thresholds)
--
-- Schema conventions:
--   * All primary keys are either natural keys or UUID TEXT — no SERIAL ints.
--     UUID TEXT avoids cross-service coordination when generating IDs.
--   * Timestamps are TIMESTAMPTZ (always UTC). Never store naive timestamps.
--   * Numeric precision: sensor values use NUMERIC(10,4) to preserve simulator fidelity.
--   * Indexes are named explicitly so migrations can drop/recreate them by name.

-- ==========================================================================
-- Extensions
-- ==========================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- uuid_generate_v4() fallback


-- ==========================================================================
-- Reference data
-- ==========================================================================

CREATE TABLE IF NOT EXISTS buildings (
    id          TEXT        PRIMARY KEY,       -- e.g. 'EF', 'IT', 'NA'
    name        TEXT        NOT NULL,          -- e.g. 'Engineering Faculty'
    lat         NUMERIC(9,6),                  -- WGS-84 centroid
    lon         NUMERIC(9,6),
    floors      INT         NOT NULL CHECK (floors >= 1),
    capacity    INT         NOT NULL CHECK (capacity >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE buildings IS
    'Physical campus buildings. Populated once from the simulator topology.';

CREATE TABLE IF NOT EXISTS rooms (
    id          TEXT        PRIMARY KEY,       -- e.g. 'EF101'
    building_id TEXT        NOT NULL REFERENCES buildings(id),
    floor       INT         NOT NULL CHECK (floor >= 0),
    room_type   TEXT        NOT NULL,          -- classroom | lab | canteen | library | ...
    capacity    INT         NOT NULL CHECK (capacity >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE rooms IS
    'Individual rooms within buildings. Used as a lookup for capacity checks in Flink.';

CREATE INDEX IF NOT EXISTS idx_rooms_building
    ON rooms (building_id);


-- ==========================================================================
-- Operational data — written by Spark / Flink at runtime
-- ==========================================================================

CREATE TABLE IF NOT EXISTS energy_daily (
    -- Natural composite PK: one row per (day, building)
    date         DATE        NOT NULL,
    building_id  TEXT        NOT NULL REFERENCES buildings(id),
    total_kwh    NUMERIC(12, 3) NOT NULL CHECK (total_kwh >= 0),
    peak_w       NUMERIC(10, 2) NOT NULL CHECK (peak_w >= 0),
    avg_w        NUMERIC(10, 2) NOT NULL CHECK (avg_w >= 0),
    sample_hours INT         NOT NULL DEFAULT 24
        CHECK (sample_hours BETWEEN 1 AND 24),  -- < 24 flags a partial day
    written_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, building_id)
);

COMMENT ON TABLE energy_daily IS
    'Per-building daily energy summary. Written by Spark DailyEnergyReportJob via Airflow.
     Use sample_hours < 24 to flag days with missing hourly data.';

CREATE INDEX IF NOT EXISTS idx_energy_daily_building_date
    ON energy_daily (building_id, date DESC);


CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id   TEXT        PRIMARY KEY,      -- UUID v4 from AnomalyEvent.anomaly_id
    detected_at  TIMESTAMPTZ NOT NULL,
    sensor_id    TEXT        NOT NULL,
    -- No FK to buildings: Flink writes anomalies in real-time before buildings
    -- are seeded, and FK violations would silently drop anomaly rows.
    building_id  TEXT        NOT NULL,
    floor        INT         NOT NULL,
    room_id      TEXT        NOT NULL,
    sensor_type  TEXT        NOT NULL,
    anomaly_type TEXT        NOT NULL,
    severity     TEXT        NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    value        NUMERIC(10, 4) NOT NULL,
    threshold    NUMERIC(10, 4) NOT NULL,
    message      TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE anomalies IS
    'Anomaly audit log written by Flink AnomalyJob. Immutable — never UPDATE rows here.
     Use for dashboard alert queries and post-incident review.';

CREATE INDEX IF NOT EXISTS idx_anomalies_detected_at
    ON anomalies (detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_anomalies_building_type
    ON anomalies (building_id, anomaly_type, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_anomalies_severity
    ON anomalies (severity, detected_at DESC);


CREATE TABLE IF NOT EXISTS ml_energy_features (
    -- One row per (date, building_id) for daily energy prediction
    date             DATE        NOT NULL,
    building_id      TEXT        NOT NULL REFERENCES buildings(id),
    building_type    TEXT        NOT NULL,
    total_capacity   INT,
    n_rooms          INT,
    avg_occ_ratio    NUMERIC(5, 4)  CHECK (avg_occ_ratio BETWEEN 0 AND 1),
    is_weekend       BOOLEAN     NOT NULL,
    is_holiday       BOOLEAN     NOT NULL,
    holiday_name     TEXT,
    total_energy_kwh NUMERIC(12, 3),
    data_completeness NUMERIC(4, 3) CHECK (data_completeness BETWEEN 0 AND 1),
    written_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, building_id)
);

COMMENT ON TABLE ml_energy_features IS
    'Daily per-building feature vectors for Energy ML model training and evaluation.
     Written by Airflow DAGs.
     data_completeness = fraction of expected hourly windows that had data.';

CREATE INDEX IF NOT EXISTS idx_ml_energy_features_bld_date
    ON ml_energy_features (building_id, date DESC);


-- ==========================================================================
-- Configuration — read by Flink AnomalyJob at startup
-- ==========================================================================

CREATE TABLE IF NOT EXISTS alert_rules (
    id           SERIAL      PRIMARY KEY,
    sensor_type  TEXT        NOT NULL,
    anomaly_type TEXT        NOT NULL,
    threshold    NUMERIC(10, 4) NOT NULL,
    severity     TEXT        NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    enabled      BOOLEAN     NOT NULL DEFAULT true,
    description  TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sensor_type, anomaly_type)
);

COMMENT ON TABLE alert_rules IS
    'Configurable anomaly detection thresholds. Read by Flink AnomalyJob on startup.
     Update rows here and restart the job to change thresholds without code changes.';

-- Seed default rules matching the values documented in PIPELINE_ARCHITECTURE.md
INSERT INTO alert_rules (sensor_type, anomaly_type, threshold, severity, description)
VALUES
    ('temperature', 'threshold_high', 38.0,  'warning',  'Room temperature above 38°C'),
    ('temperature', 'threshold_low',  14.0,  'warning',  'Room temperature below 14°C'),
    ('energy',      'spike',          3.0,   'warning',  'Energy > 3× 5-min rolling average'),
    ('occupancy',   'capacity_breach', 1.05, 'critical', 'Occupancy > 105% room capacity')
ON CONFLICT (sensor_type, anomaly_type) DO NOTHING;


-- ==========================================================================
-- Staging tables — used by Spark JDBC upsert pattern
-- (write here first, then merge into the real table with ON CONFLICT)
-- Spark's DataFrame.write.jdbc mode="overwrite" truncates these each run.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS energy_daily_staging (
    date         DATE,
    building_id  TEXT,
    total_kwh    NUMERIC(12, 3),
    peak_w       NUMERIC(10, 2),
    avg_w        NUMERIC(10, 2),
    sample_hours INT
);

CREATE TABLE IF NOT EXISTS ml_energy_features_staging (
    date              DATE,
    building_id       TEXT,
    building_type     TEXT,
    total_capacity    INT,
    n_rooms           INT,
    avg_occ_ratio     NUMERIC(5, 4),
    is_weekend        BOOLEAN,
    is_holiday        BOOLEAN,
    holiday_name      TEXT,
    total_energy_kwh  NUMERIC(12, 3),
    data_completeness NUMERIC(4, 3)
);
