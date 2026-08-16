EXEC(N'CREATE VIEW register.aggregate_status_v1
AS
SELECT owning_application, aggregate_id, aggregate_version, last_command_id, updated_at
FROM register.aggregate_current;');

EXEC(N'CREATE VIEW register.recovery_export_rows_v1
AS
SELECT CAST(''COMMAND'' AS varchar(24)) AS fact_family,
       command_id AS fact_id, command_fingerprint AS fact_fingerprint,
       command_bytes AS fact_bytes, recorded_at
FROM register.command_v1_fact
UNION ALL
SELECT ''EVENT'', event_id, event_fingerprint, event_bytes, recorded_at
FROM register.event_v1_fact
UNION ALL
SELECT ''EFFECT_INTENT'', effect_intent_id, intent_fingerprint, intent_bytes, recorded_at
FROM register.effect_intent_fact
UNION ALL
SELECT ''EFFECT_ATTEMPT'', CONCAT(effect_intent_id, '':'', attempt_number),
       event_fingerprint, event_bytes, recorded_at
FROM register.effect_attempt_fact
UNION ALL
SELECT ''EFFECT_RECEIPT'', effect_receipt_id, receipt_fingerprint, receipt_bytes, recorded_at
FROM register.effect_receipt_fact;');

EXEC(N'CREATE VIEW register.effect_status_v1
AS
SELECT i.effect_intent_id, i.owning_application, i.effect_type, i.deadline,
       c.claimant_id, c.generation, c.fencing_token, c.expires_at,
       r.effect_receipt_id, r.terminal_status, r.attempt_count
FROM register.effect_intent_fact i
LEFT JOIN register.effect_claim_current c ON c.effect_intent_id = i.effect_intent_id
LEFT JOIN register.effect_receipt_fact r ON r.effect_intent_id = i.effect_intent_id;');

GRANT EXECUTE ON OBJECT::register.commit_command_v1 TO asklegal_control_role;
GRANT EXECUTE ON OBJECT::register.commit_command_v1 TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::register.commit_command_v1 TO asklegal_acquisition_role;
GRANT EXECUTE ON OBJECT::register.commit_command_v1 TO asklegal_legal_processing_role;
GRANT EXECUTE ON OBJECT::register.commit_command_v1 TO asklegal_promotion_role;
GRANT EXECUTE ON OBJECT::register.resolve_command_v1 TO asklegal_control_role;
GRANT EXECUTE ON OBJECT::register.resolve_command_v1 TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::register.resolve_command_v1 TO asklegal_acquisition_role;
GRANT EXECUTE ON OBJECT::register.resolve_command_v1 TO asklegal_legal_processing_role;
GRANT EXECUTE ON OBJECT::register.resolve_command_v1 TO asklegal_promotion_role;
GRANT EXECUTE ON OBJECT::register.claim_effect_v1 TO asklegal_control_role;
GRANT EXECUTE ON OBJECT::register.claim_effect_v1 TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::register.claim_effect_v1 TO asklegal_acquisition_role;
GRANT EXECUTE ON OBJECT::register.claim_effect_v1 TO asklegal_legal_processing_role;
GRANT EXECUTE ON OBJECT::register.claim_effect_v1 TO asklegal_promotion_role;
GRANT EXECUTE ON OBJECT::register.renew_effect_claim_v1 TO asklegal_control_role;
GRANT EXECUTE ON OBJECT::register.renew_effect_claim_v1 TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::register.renew_effect_claim_v1 TO asklegal_acquisition_role;
GRANT EXECUTE ON OBJECT::register.renew_effect_claim_v1 TO asklegal_legal_processing_role;
GRANT EXECUTE ON OBJECT::register.renew_effect_claim_v1 TO asklegal_promotion_role;
GRANT EXECUTE ON OBJECT::register.append_effect_attempt_v1 TO asklegal_control_role;
GRANT EXECUTE ON OBJECT::register.append_effect_attempt_v1 TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::register.append_effect_attempt_v1 TO asklegal_acquisition_role;
GRANT EXECUTE ON OBJECT::register.append_effect_attempt_v1 TO asklegal_legal_processing_role;
GRANT EXECUTE ON OBJECT::register.append_effect_attempt_v1 TO asklegal_promotion_role;
GRANT EXECUTE ON OBJECT::register.record_effect_receipt_v1 TO asklegal_control_role;
GRANT EXECUTE ON OBJECT::register.record_effect_receipt_v1 TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::register.record_effect_receipt_v1 TO asklegal_acquisition_role;
GRANT EXECUTE ON OBJECT::register.record_effect_receipt_v1 TO asklegal_legal_processing_role;
GRANT EXECUTE ON OBJECT::register.record_effect_receipt_v1 TO asklegal_promotion_role;
GRANT SELECT ON OBJECT::register.aggregate_status_v1 TO asklegal_control_role;
GRANT SELECT ON OBJECT::register.aggregate_status_v1 TO asklegal_review_role;
GRANT SELECT ON OBJECT::register.aggregate_status_v1 TO asklegal_acquisition_role;
GRANT SELECT ON OBJECT::register.aggregate_status_v1 TO asklegal_legal_processing_role;
GRANT SELECT ON OBJECT::register.aggregate_status_v1 TO asklegal_promotion_role;
GRANT SELECT ON OBJECT::register.effect_status_v1 TO asklegal_control_role;
GRANT SELECT ON OBJECT::register.effect_status_v1 TO asklegal_review_role;
GRANT SELECT ON OBJECT::register.effect_status_v1 TO asklegal_acquisition_role;
GRANT SELECT ON OBJECT::register.effect_status_v1 TO asklegal_legal_processing_role;
GRANT SELECT ON OBJECT::register.effect_status_v1 TO asklegal_promotion_role;

DENY INSERT, UPDATE, DELETE ON SCHEMA::register TO asklegal_control_role;
DENY INSERT, UPDATE, DELETE ON SCHEMA::register TO asklegal_acquisition_role;
DENY INSERT, UPDATE, DELETE ON SCHEMA::register TO asklegal_legal_processing_role;
