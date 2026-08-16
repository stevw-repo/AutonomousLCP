SET XACT_ABORT ON;

EXEC(N'CREATE SCHEMA control AUTHORIZATION dbo;');
EXEC(N'CREATE SCHEMA acquisition AUTHORIZATION dbo;');
EXEC(N'CREATE SCHEMA legal_processing AUTHORIZATION dbo;');

CREATE TABLE register.aggregate_current
(
    owning_application varchar(48) NOT NULL,
    aggregate_id varchar(80) NOT NULL,
    aggregate_version bigint NOT NULL,
    last_command_id varchar(80) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT pk_aggregate_current PRIMARY KEY (owning_application, aggregate_id),
    CONSTRAINT ck_aggregate_version_positive CHECK (aggregate_version >= 1)
);

CREATE TABLE register.command_v1_fact
(
    owning_application varchar(48) NOT NULL,
    command_id varchar(80) NOT NULL,
    command_fingerprint binary(32) NOT NULL,
    command_bytes varbinary(max) NOT NULL,
    target_id varchar(80) NOT NULL,
    expected_version bigint NULL,
    expected_absent bit NOT NULL,
    result_code varchar(48) NOT NULL,
    authoritative_version bigint NULL,
    result_bytes varbinary(max) NOT NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_command_v1_expected CHECK
        ((expected_absent = 1 AND expected_version IS NULL) OR
         (expected_absent = 0 AND expected_version >= 0)),
    CONSTRAINT ck_command_v1_result CHECK
        (result_code IN
        (
            'APPLIED', 'REJECTED_STALE_VERSION', 'REJECTED_INVALID_STATE',
            'REJECTED_INVALID_INPUT', 'REJECTED_UNAUTHORIZED', 'REJECTED_EXPIRED',
            'REJECTED_CONFLICT', 'REJECTED_CAPABILITY'
        )),
    CONSTRAINT ck_command_v1_bytes CHECK
        (DATALENGTH(command_bytes) > 1 AND DATALENGTH(result_bytes) > 1)
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_command_v1_identity
    ON register.command_v1_fact(owning_application, command_id);

CREATE TABLE register.event_v1_fact
(
    event_id varchar(80) NOT NULL,
    owning_application varchar(48) NOT NULL,
    command_id varchar(80) NOT NULL,
    aggregate_id varchar(80) NOT NULL,
    event_type varchar(80) NOT NULL,
    prior_version bigint NOT NULL,
    new_version bigint NOT NULL,
    event_bytes varbinary(max) NOT NULL,
    event_fingerprint binary(32) NOT NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_event_v1_version CHECK
        (prior_version >= 0 AND new_version = prior_version + 1),
    CONSTRAINT ck_event_v1_bytes CHECK (DATALENGTH(event_bytes) > 1)
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_event_v1_identity ON register.event_v1_fact(event_id);
CREATE UNIQUE INDEX ux_event_v1_aggregate_version
    ON register.event_v1_fact(owning_application, aggregate_id, new_version);

CREATE TABLE register.effect_intent_fact
(
    effect_intent_id varchar(80) NOT NULL,
    owning_application varchar(48) NOT NULL,
    command_id varchar(80) NOT NULL,
    aggregate_id varchar(80) NOT NULL,
    effect_type varchar(48) NOT NULL,
    intent_bytes varbinary(max) NOT NULL,
    intent_fingerprint binary(32) NOT NULL,
    deadline datetime2(7) NOT NULL,
    attempt_ceiling int NOT NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_effect_intent_attempts CHECK (attempt_ceiling >= 1),
    CONSTRAINT ck_effect_intent_bytes CHECK (DATALENGTH(intent_bytes) > 1)
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_effect_intent_identity
    ON register.effect_intent_fact(effect_intent_id);

CREATE TABLE register.single_winner_current
(
    winner_key varchar(160) NOT NULL CONSTRAINT pk_single_winner_current PRIMARY KEY,
    command_id varchar(80) NOT NULL,
    recorded_at datetime2(7) NOT NULL
);

CREATE TABLE register.effect_claim_current
(
    effect_intent_id varchar(80) NOT NULL CONSTRAINT pk_effect_claim_current PRIMARY KEY,
    claimant_id varchar(80) NOT NULL,
    generation bigint NOT NULL,
    fencing_token bigint NOT NULL,
    claimed_at datetime2(7) NOT NULL,
    expires_at datetime2(7) NOT NULL,
    CONSTRAINT ck_effect_claim_counters CHECK (generation >= 1 AND fencing_token >= 1),
    CONSTRAINT ck_effect_claim_time CHECK (expires_at > claimed_at)
);

CREATE TABLE register.effect_attempt_fact
(
    effect_intent_id varchar(80) NOT NULL,
    attempt_number int NOT NULL,
    fencing_token bigint NOT NULL,
    event_code varchar(48) NOT NULL,
    event_bytes varbinary(max) NOT NULL,
    event_fingerprint binary(32) NOT NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_effect_attempt_number CHECK (attempt_number >= 1),
    CONSTRAINT ck_effect_attempt_fence CHECK (fencing_token >= 1),
    CONSTRAINT ck_effect_attempt_bytes CHECK (DATALENGTH(event_bytes) > 1)
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_effect_attempt_number
    ON register.effect_attempt_fact(effect_intent_id, attempt_number);

CREATE TABLE register.effect_receipt_fact
(
    effect_receipt_id varchar(80) NOT NULL,
    effect_intent_id varchar(80) NOT NULL,
    terminal_status varchar(32) NOT NULL,
    attempt_count int NOT NULL,
    receipt_bytes varbinary(max) NOT NULL,
    receipt_fingerprint binary(32) NOT NULL,
    fencing_token bigint NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_effect_receipt_status CHECK
        (terminal_status IN
        ('SUCCEEDED', 'FAILED_FINAL', 'CANCELLED_BEFORE_EFFECT', 'OUTCOME_UNKNOWN')),
    CONSTRAINT ck_effect_receipt_attempts CHECK
        ((terminal_status = 'CANCELLED_BEFORE_EFFECT' AND attempt_count = 0 AND
          fencing_token IS NULL) OR
         (terminal_status <> 'CANCELLED_BEFORE_EFFECT' AND attempt_count >= 1 AND
          fencing_token >= 1)),
    CONSTRAINT ck_effect_receipt_bytes CHECK (DATALENGTH(receipt_bytes) > 1)
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE UNIQUE INDEX ux_effect_receipt_identity
    ON register.effect_receipt_fact(effect_receipt_id);
CREATE UNIQUE INDEX ux_effect_receipt_terminal
    ON register.effect_receipt_fact(effect_intent_id);

CREATE TABLE register.policy_state_fact
(
    policy_id varchar(80) NOT NULL,
    policy_fingerprint binary(32) NOT NULL,
    state_code varchar(16) NOT NULL,
    value_id varchar(80) NULL,
    value_fingerprint binary(32) NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_policy_state_code CHECK (state_code IN ('CONFIGURED', 'UNDECIDED')),
    CONSTRAINT ck_policy_state_value CHECK
        ((state_code = 'CONFIGURED' AND value_id IS NOT NULL AND value_fingerprint IS NOT NULL) OR
         (state_code = 'UNDECIDED' AND value_id IS NULL AND value_fingerprint IS NULL))
) WITH (LEDGER = ON (APPEND_ONLY = ON));

CREATE TABLE register.projection_checkpoint_current
(
    projection_name varchar(80) NOT NULL CONSTRAINT pk_projection_checkpoint PRIMARY KEY,
    source_event_id varchar(80) NULL,
    source_event_fingerprint binary(32) NULL,
    checkpoint_sequence bigint NOT NULL,
    rebuilt_at datetime2(7) NOT NULL,
    CONSTRAINT ck_projection_checkpoint_nonnegative CHECK (checkpoint_sequence >= 0)
);

CREATE ROLE asklegal_control_role AUTHORIZATION dbo;
CREATE ROLE asklegal_acquisition_role AUTHORIZATION dbo;
CREATE ROLE asklegal_legal_processing_role AUTHORIZATION dbo;
CREATE USER asklegal_control_app WITHOUT LOGIN;
CREATE USER asklegal_acquisition_app WITHOUT LOGIN;
CREATE USER asklegal_legal_processing_app WITHOUT LOGIN;
ALTER ROLE asklegal_control_role ADD MEMBER asklegal_control_app;
ALTER ROLE asklegal_acquisition_role ADD MEMBER asklegal_acquisition_app;
ALTER ROLE asklegal_legal_processing_role ADD MEMBER asklegal_legal_processing_app;
