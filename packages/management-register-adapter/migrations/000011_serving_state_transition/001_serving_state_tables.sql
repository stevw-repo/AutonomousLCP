CREATE TABLE promotion.serving_state_v1_current
(
    singleton_id tinyint NOT NULL CONSTRAINT pk_serving_state_v1_current PRIMARY KEY,
    state_id varchar(80) NOT NULL,
    last_receipt_id varchar(80) NOT NULL,
    updated_at datetime2(7) NOT NULL,
    CONSTRAINT ck_serving_state_v1_singleton CHECK (singleton_id = 1)
);
CREATE TABLE promotion.serving_state_v1_fact
(
    receipt_id varchar(80) NOT NULL CONSTRAINT pk_serving_state_v1_fact PRIMARY KEY,
    operation_code varchar(24) NOT NULL,
    predecessor_state_id varchar(80) NOT NULL,
    state_id varchar(80) NOT NULL,
    state_fingerprint varchar(71) NOT NULL,
    target_name varchar(80) NOT NULL,
    desired_inventory_fingerprint varchar(71) NOT NULL,
    coverage_fingerprint varchar(71) NOT NULL,
    embedding_profile_id varchar(80) NOT NULL,
    embedding_profile_fingerprint varchar(71) NOT NULL,
    approval_id varchar(80) NOT NULL,
    execution_lineage_id varchar(80) NOT NULL,
    recorded_at datetime2(7) NOT NULL,
    CONSTRAINT ck_serving_state_v1_operation CHECK (operation_code IN ('ACTIVATED', 'ROLLED_BACK'))
) WITH (LEDGER = ON (APPEND_ONLY = ON));
CREATE UNIQUE INDEX ux_serving_state_v1_activate_replay
    ON promotion.serving_state_v1_fact
       (operation_code, predecessor_state_id, state_id, state_fingerprint, target_name,
        desired_inventory_fingerprint, coverage_fingerprint, embedding_profile_id,
        embedding_profile_fingerprint, approval_id, execution_lineage_id)
    WHERE operation_code = 'ACTIVATED';
