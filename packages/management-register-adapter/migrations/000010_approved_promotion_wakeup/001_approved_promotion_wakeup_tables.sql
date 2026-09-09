CREATE TABLE promotion.approved_promotion_claim_current
(
    approval_id varchar(80) NOT NULL
        CONSTRAINT pk_approved_promotion_claim_current PRIMARY KEY,
    proposal_package_id varchar(80) NOT NULL,
    decision_fingerprint binary(32) NOT NULL,
    manifest_id varchar(80) NOT NULL,
    manifest_fingerprint varchar(71) NOT NULL,
    claimant_worker_id varchar(80) NOT NULL,
    claimed_at datetime2(7) NOT NULL,
    claimed_until datetime2(7) NOT NULL,
    generation bigint NOT NULL,
    fencing_token bigint NOT NULL,
    CONSTRAINT ck_approved_promotion_claim_counters CHECK
        (generation >= 1 AND fencing_token >= 1),
    CONSTRAINT ck_approved_promotion_claim_times CHECK (claimed_until > claimed_at)
);

CREATE TABLE promotion.approved_promotion_acknowledgement_fact
(
    approval_id varchar(80) NOT NULL
        CONSTRAINT pk_approved_promotion_acknowledgement_fact PRIMARY KEY,
    proposal_package_id varchar(80) NOT NULL,
    decision_fingerprint binary(32) NOT NULL,
    manifest_id varchar(80) NOT NULL,
    manifest_fingerprint varchar(71) NOT NULL,
    claimant_worker_id varchar(80) NOT NULL,
    claimed_until datetime2(7) NOT NULL,
    generation bigint NOT NULL,
    fencing_token bigint NOT NULL,
    execution_lineage_id varchar(80) NOT NULL,
    acknowledged_at datetime2(7) NOT NULL,
    CONSTRAINT ck_approved_promotion_acknowledgement_counters CHECK
        (generation >= 1 AND fencing_token >= 1)
) WITH (LEDGER = ON (APPEND_ONLY = ON));
