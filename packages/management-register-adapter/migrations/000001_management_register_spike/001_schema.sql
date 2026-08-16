SET XACT_ABORT ON;

EXEC(N'CREATE SCHEMA migration AUTHORIZATION dbo;');
EXEC(N'CREATE SCHEMA register AUTHORIZATION dbo;');
EXEC(N'CREATE SCHEMA review AUTHORIZATION dbo;');
EXEC(N'CREATE SCHEMA promotion AUTHORIZATION dbo;');

CREATE TABLE migration.applied_fact
(
    migration_id char(6) NOT NULL,
    package_fingerprint binary(32) NOT NULL,
    runner_build varchar(64) NOT NULL,
    database_name sysname NOT NULL,
    executor_name sysname NOT NULL,
    applied_at datetime2(7) NOT NULL
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_applied_fact_migration_id
    ON migration.applied_fact(migration_id);

CREATE TABLE register.command_fact
(
    command_id varchar(80) NOT NULL,
    command_fingerprint binary(32) NOT NULL,
    command_bytes varbinary(max) NOT NULL,
    result_code varchar(48) NOT NULL,
    result_bytes varbinary(max) NOT NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_command_bytes_not_empty CHECK (DATALENGTH(command_bytes) > 1),
    CONSTRAINT ck_result_bytes_not_empty CHECK (DATALENGTH(result_bytes) > 1)
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_command_fact_command_id
    ON register.command_fact(command_id);

CREATE TABLE register.inbox_fact
(
    command_id varchar(80) NOT NULL,
    command_fingerprint binary(32) NOT NULL,
    claimed_at datetime2(7) NOT NULL
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_inbox_fact_command_id
    ON register.inbox_fact(command_id);

CREATE TABLE register.lifecycle_fact
(
    event_id uniqueidentifier NOT NULL,
    object_type varchar(48) NOT NULL,
    object_id varchar(80) NOT NULL,
    lifecycle_code varchar(48) NOT NULL,
    command_id varchar(80) NOT NULL,
    payload_bytes varbinary(max) NOT NULL,
    payload_fingerprint binary(32) NOT NULL,
    recorded_at datetime2(7) NOT NULL
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_lifecycle_fact_event_id
    ON register.lifecycle_fact(event_id);

CREATE TABLE register.outbox_fact
(
    intent_id uniqueidentifier NOT NULL,
    command_id varchar(80) NOT NULL,
    intent_type varchar(48) NOT NULL,
    intent_bytes varbinary(max) NOT NULL,
    intent_fingerprint binary(32) NOT NULL,
    recorded_at datetime2(7) NOT NULL
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_outbox_fact_intent_id
    ON register.outbox_fact(intent_id);

CREATE TABLE review.approval_current
(
    approval_id varchar(80) NOT NULL
        CONSTRAINT pk_approval_current PRIMARY KEY,
    manifest_fingerprint binary(32) NOT NULL,
    state_code varchar(32) NOT NULL,
    consumed_by_command_id varchar(80) NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT ck_approval_state CHECK (state_code IN ('VALID', 'CONSUMED'))
);

CREATE TABLE promotion.serving_state_current
(
    singleton_id tinyint NOT NULL
        CONSTRAINT pk_serving_state_current PRIMARY KEY,
    manifest_fingerprint binary(32) NOT NULL,
    activation_command_id varchar(80) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT ck_serving_singleton CHECK (singleton_id = 1)
);

CREATE ROLE asklegal_review_role AUTHORIZATION dbo;
CREATE ROLE asklegal_promotion_role AUTHORIZATION dbo;
CREATE USER asklegal_review_app WITHOUT LOGIN;
CREATE USER asklegal_promotion_app WITHOUT LOGIN;
ALTER ROLE asklegal_review_role ADD MEMBER asklegal_review_app;
ALTER ROLE asklegal_promotion_role ADD MEMBER asklegal_promotion_app;

EXEC(N'CREATE VIEW review.approval_status
AS
SELECT approval_id, manifest_fingerprint, state_code, consumed_by_command_id, updated_at
FROM review.approval_current;');

EXEC(N'CREATE VIEW promotion.serving_state
AS
SELECT manifest_fingerprint, activation_command_id, updated_at
FROM promotion.serving_state_current;');

GRANT SELECT ON OBJECT::review.approval_status TO asklegal_review_role;
GRANT SELECT ON OBJECT::promotion.serving_state TO asklegal_promotion_role;
