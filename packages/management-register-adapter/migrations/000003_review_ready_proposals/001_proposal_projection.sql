EXEC(N'CREATE VIEW review.proposal_package_status_v1
AS
SELECT e.aggregate_id AS proposal_package_id,
       e.event_bytes AS receipt_bytes,
       e.event_fingerprint AS receipt_fingerprint,
       e.new_version AS authoritative_version,
       e.recorded_at AS review_ready_at
FROM register.event_v1_fact e
WHERE e.owning_application = ''CONTROL_PLANE''
  AND e.event_type = ''PROPOSAL_REVIEW_READY'';');

GRANT SELECT ON OBJECT::review.proposal_package_status_v1 TO asklegal_control_role;
GRANT SELECT ON OBJECT::review.proposal_package_status_v1 TO asklegal_review_role;
GRANT SELECT ON OBJECT::review.proposal_package_status_v1 TO asklegal_promotion_role;
