-- Soccer Predictions Platform - Database Initialization Script
-- This script creates the multi-schema database architecture
-- Based on the database schema documentation in docs/database/

-- ============================================================================
-- SECTION 1: CREATE SCHEMAS
-- ============================================================================

-- Create the five primary schemas for the platform
CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS predictions;
CREATE SCHEMA IF NOT EXISTS ml_models;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS audit;

-- Set search path to include all schemas
ALTER DATABASE soccer_predictions SET search_path TO users, predictions, ml_models, analytics, audit, public;

-- ============================================================================
-- SECTION 2: ENABLE EXTENSIONS
-- ============================================================================

-- UUID generation for primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- JSONB operations and indexing
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Full-text search capabilities
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Cryptographic functions for password hashing
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- SECTION 3: CREATE CUSTOM TYPES (ENUMS)
-- ============================================================================

-- User-related enums
CREATE TYPE users.user_role AS ENUM ('regular', 'expert', 'admin');
CREATE TYPE users.subscription_tier AS ENUM ('free', 'basic', 'premium', 'pro');
CREATE TYPE users.verification_status AS ENUM ('pending', 'verified', 'rejected', 'suspended');

-- Prediction-related enums
CREATE TYPE predictions.prediction_source AS ENUM ('ml_baseline', 'expert_created', 'expert_override', 'admin_created', 'admin_override');
CREATE TYPE predictions.prediction_status AS ENUM ('draft', 'pending_review', 'approved', 'published', 'settled', 'void', 'cancelled');
CREATE TYPE predictions.betting_market AS ENUM ('1x2', 'btts', 'over_under', 'correct_score', 'double_chance', 'handicap');
CREATE TYPE predictions.confidence_level AS ENUM ('low', 'medium', 'high', 'very_high');
CREATE TYPE predictions.match_status AS ENUM ('scheduled', 'live', 'finished', 'postponed', 'cancelled', 'abandoned');

-- ML model-related enums
CREATE TYPE ml_models.model_status AS ENUM ('development', 'testing', 'staging', 'production', 'deprecated', 'archived');
CREATE TYPE ml_models.model_type AS ENUM ('random_forest', 'xgboost', 'neural_network', 'ensemble');

-- Audit-related enums
CREATE TYPE audit.event_category AS ENUM ('authentication', 'authorization', 'data_access', 'data_modification', 'system', 'security');
CREATE TYPE audit.severity AS ENUM ('info', 'warning', 'error', 'critical');

-- ============================================================================
-- SECTION 4: CREATE UTILITY FUNCTIONS
-- ============================================================================

-- Function to update updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to generate unique slugs
CREATE OR REPLACE FUNCTION generate_slug(text_input TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN lower(regexp_replace(text_input, '[^a-zA-Z0-9]+', '-', 'g'));
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SECTION 5: GRANT PERMISSIONS
-- ============================================================================

-- Grant usage on schemas to postgres user
GRANT USAGE ON SCHEMA users TO postgres;
GRANT USAGE ON SCHEMA predictions TO postgres;
GRANT USAGE ON SCHEMA ml_models TO postgres;
GRANT USAGE ON SCHEMA analytics TO postgres;
GRANT USAGE ON SCHEMA audit TO postgres;

-- Grant all privileges on all tables in schemas
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA users TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA predictions TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ml_models TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA analytics TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO postgres;

-- Grant all privileges on all sequences in schemas
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA users TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA predictions TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA ml_models TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA analytics TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit TO postgres;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA users GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA predictions GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA ml_models GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT ALL ON TABLES TO postgres;

-- ============================================================================
-- SECTION 6: CREATE LOGGING TABLE
-- ============================================================================

-- Create a simple logging table for database initialization tracking
CREATE TABLE IF NOT EXISTS public.db_init_log (
    id SERIAL PRIMARY KEY,
    script_name VARCHAR(255) NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'success',
    message TEXT
);

-- Log this initialization
INSERT INTO public.db_init_log (script_name, message)
VALUES ('01-init-database.sql', 'Database schemas, extensions, and types created successfully');

-- ============================================================================
-- SECTION 7: DISPLAY INFORMATION
-- ============================================================================

-- Display created schemas
DO $$
BEGIN
    RAISE NOTICE '✅ Database initialization complete!';
    RAISE NOTICE '📊 Created schemas: users, predictions, ml_models, analytics, audit';
    RAISE NOTICE '🔧 Enabled extensions: uuid-ossp, btree_gin, pg_trgm, pgcrypto';
    RAISE NOTICE '📝 Created custom types (enums) for all schemas';
    RAISE NOTICE '🔐 Granted permissions to postgres user';
    RAISE NOTICE '';
    RAISE NOTICE '🚀 Next steps:';
    RAISE NOTICE '   1. Run Alembic migrations to create tables';
    RAISE NOTICE '   2. Run seed data scripts to populate initial data';
    RAISE NOTICE '   3. Connect backend application to database';
    RAISE NOTICE '';
    RAISE NOTICE '📖 For more information, see docs/database/README.md';
END $$;

