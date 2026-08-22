EXEC(N'CREATE VIEW review.proposal_package_review_v1
AS
SELECT ready.aggregate_id AS proposal_package_id,
       ready.event_bytes AS receipt_bytes,
       ready.event_fingerprint AS receipt_fingerprint,
       ready.new_version AS registration_version,
       ready.recorded_at AS review_ready_at,
       decision.event_bytes AS decision_bytes,
       decision.event_fingerprint AS decision_fingerprint,
       ISNULL(decision.new_version, 0) AS review_version,
       decision.event_type AS decision_event_type,
       decision.recorded_at AS decision_at
FROM register.event_v1_fact ready
LEFT JOIN register.event_v1_fact decision
  ON decision.aggregate_id = ready.aggregate_id
 AND decision.owning_application = ''REVIEW_APPLICATION''
 AND decision.event_type IN (''PROPOSAL_APPROVED'', ''PROPOSAL_REJECTED'')
WHERE ready.owning_application = ''CONTROL_PLANE''
  AND ready.event_type = ''PROPOSAL_REVIEW_READY'';');

GRANT SELECT ON OBJECT::review.proposal_package_review_v1 TO asklegal_review_role;
GRANT SELECT ON OBJECT::review.proposal_package_review_v1 TO asklegal_promotion_role;
