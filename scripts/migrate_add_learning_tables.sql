-- Migration: add user_merchant_map and classification_audit_log tables
-- Run once against the Neon PostgreSQL database before deploying the updated backend.
--
-- user_merchant_map  : stores user corrections as personalised merchant overrides (Layer 0)
-- classification_audit_log : full audit trail of every AI classification and human review

-- Enable UUID extension (already present on Neon, but safe to re-run)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── user_merchant_map ────────────────────────────────────────────────────────────
-- Each row records a user's correction of a merchant → category mapping.
-- The Categorization Agent checks this table before the global merchant map (Layer 0).
CREATE TABLE IF NOT EXISTS user_merchant_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(255) NOT NULL,
    merchant_key    VARCHAR(255) NOT NULL,      -- lowercase, normalised merchant name
    category        VARCHAR(50)  NOT NULL,      -- must match CategoryEnum values
    confidence      FLOAT        DEFAULT 1.0,
    learn_count     INTEGER      DEFAULT 1,     -- incremented each time same merchant is corrected
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,

    CONSTRAINT uq_user_merchant UNIQUE (user_id, merchant_key)
);

CREATE INDEX IF NOT EXISTS ix_user_merchant_map_user_id
    ON user_merchant_map (user_id);

-- ── classification_audit_log ─────────────────────────────────────────────────────
-- Immutable append-only log: one row per classification event or review action.
-- Supports IMDA Model AI Governance Framework traceability requirements.
CREATE TABLE IF NOT EXISTS classification_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id  UUID         NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    user_id         VARCHAR(255) NOT NULL,

    event_type      VARCHAR(30)  NOT NULL,
    -- Allowed values:
    --   'ai_classified'   : agent produced an automatic classification
    --   'human_confirmed' : user accepted the AI suggestion
    --   'human_corrected' : user overrode the AI suggestion

    decision_source VARCHAR(30),               -- merchant_map | llm | … | user_corrected
    old_category    VARCHAR(50),
    new_category    VARCHAR(50),
    confidence      FLOAT,
    evidence        TEXT,
    actor           VARCHAR(10),               -- 'agent' | 'human'
    meta            JSONB,                     -- extra debug info (trace, elapsed_ms, …)
    timestamp       TIMESTAMPTZ  DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_log_transaction_id
    ON classification_audit_log (transaction_id);

CREATE INDEX IF NOT EXISTS ix_audit_log_user_id
    ON classification_audit_log (user_id);

CREATE INDEX IF NOT EXISTS ix_audit_log_timestamp
    ON classification_audit_log (timestamp);
