CREATE PROCEDURE promotion.invalidate_registered_approval_v1
    @command_id varchar(80),
    @command_fingerprint binary(32),
    @command_bytes varbinary(max),
    @approval_id varchar(80),
    @proposal_package_id varchar(80),
    @decision_fingerprint binary(32),
    @manifest_id varchar(80),
    @manifest_fingerprint varchar(71),
    @expires_at datetime2(7),
    @event_id varchar(80),
    @event_bytes varbinary(max),
    @event_fingerprint binary(32)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

    DECLARE @decision_fingerprint_text varchar(71) =
        CONCAT('sha256:', LOWER(CONVERT(varchar(64), @decision_fingerprint, 2)));
    DECLARE @command_json varchar(max) = CONVERT(varchar(max), @command_bytes);
    DECLARE @event_json varchar(max) = CONVERT(varchar(max), @event_bytes);

    IF HASHBYTES('SHA2_256', @command_bytes) <> @command_fingerprint
        THROW 51700, 'ASKLEGAL_COMMAND_BYTES_FINGERPRINT_MISMATCH', 1;
    IF HASHBYTES('SHA2_256', @event_bytes) <> @event_fingerprint
        THROW 51701, 'ASKLEGAL_EVENT_BYTES_FINGERPRINT_MISMATCH', 1;
    IF @approval_id NOT LIKE 'apr[_]%' OR @proposal_package_id NOT LIKE 'ppk[_]%' OR
       @manifest_id NOT LIKE 'pmn[_]%' OR @event_id NOT LIKE 'ape[_]%' OR
       @manifest_fingerprint NOT LIKE 'sha256:%' OR LEN(@manifest_fingerprint) <> 71
        THROW 51702, 'ASKLEGAL_APPROVAL_INVALIDATION_IDENTITY_INVALID', 1;
    IF ISJSON(@command_json) <> 1 OR
       ISNULL(JSON_VALUE(@command_json, '$.action'), '') <>
           'INVALIDATE_REGISTERED_APPROVAL' OR
       ISNULL(JSON_VALUE(@command_json, '$.approval_id'), '') <> @approval_id OR
       ISNULL(JSON_VALUE(@command_json, '$.proposal_package_id'), '') <>
           @proposal_package_id OR
       ISNULL(JSON_VALUE(@command_json, '$.decision_fingerprint'), '') <>
           @decision_fingerprint_text OR
       ISNULL(JSON_VALUE(@command_json, '$.manifest_id'), '') <> @manifest_id OR
       ISNULL(JSON_VALUE(@command_json, '$.manifest_fingerprint'), '') <>
           @manifest_fingerprint OR
       ISNULL(JSON_VALUE(@command_json, '$.reason_code'), '') NOT IN
           ('BASE_SERVING_STATE_DRIFT', 'MANIFEST_INVALIDATED', 'MANIFEST_WINDOW_CLOSED',
            'REVIEWER_AUTHORITY_REMOVED', 'VALIDITY_PREDICATE_DRIFT')
        THROW 51703, 'ASKLEGAL_APPROVAL_INVALIDATION_COMMAND_INVALID', 1;
    IF ISJSON(@event_json) <> 1 OR
       ISNULL(JSON_VALUE(@event_json, '$.schema_id'), '') <>
           'asklegal.approval-lifecycle-event' OR
       ISNULL(JSON_VALUE(@event_json, '$.schema_version'), '') <> '1.1.0' OR
       ISNULL(JSON_VALUE(@event_json, '$.approval_lifecycle_event_id'), '') <> @event_id OR
       ISNULL(JSON_VALUE(@event_json, '$.approval_ref.ref_id'), '') <> @approval_id OR
       ISNULL(JSON_VALUE(@event_json, '$.approval_ref.fingerprint'), '') <>
           @decision_fingerprint_text OR
       ISNULL(JSON_VALUE(@event_json, '$.from_state'), '') <> 'APPROVAL_APPROVED' OR
       ISNULL(JSON_VALUE(@event_json, '$.to_state'), '') <> 'APPROVAL_INVALIDATED' OR
       ISNULL(JSON_VALUE(@event_json, '$.event_type'), '') <> 'INVALIDATE' OR
       ISNULL(JSON_VALUE(@event_json, '$.responsible_identity_ref.ref_type'), '') <> 'ACTOR' OR
       ISNULL(JSON_VALUE(@event_json, '$.responsible_identity_ref.ref_id'), '')
           NOT LIKE 'act[_]%' OR
       ISNULL(JSON_VALUE(@event_json, '$.evidence_refs[0].ref_type'), '') <> 'EVIDENCE' OR
       ISNULL(JSON_VALUE(@event_json, '$.evidence_refs[0].ref_id'), '') NOT LIKE 'evi[_]%' OR
       ISNULL(JSON_QUERY(@event_json, '$.execution_lineage_refs'), '') <> '[]' OR
       ISNULL(JSON_VALUE(@event_json, '$.immutable'), '') <> 'true'
        THROW 51704, 'ASKLEGAL_APPROVAL_INVALIDATION_EVENT_INVALID', 1;

    IF EXISTS
    (
        SELECT 1 FROM register.command_v1_fact
        WHERE owning_application = 'PROMOTION_WORKER' AND command_id = @command_id
    )
    BEGIN
        EXEC register.resolve_command_v1
            @owning_application = 'PROMOTION_WORKER',
            @command_id = @command_id,
            @command_fingerprint = @command_fingerprint;
        RETURN;
    END;

    DECLARE @lock_result int;
    DECLARE @lock_resource nvarchar(255) = CONCAT('asklegal:approval:', @approval_id);
    DECLARE @winner_key varchar(160) = CONCAT('approval-terminal:', @approval_id);

    BEGIN TRANSACTION;
    BEGIN TRY
        EXEC @lock_result = sys.sp_getapplock
            @Resource = @lock_resource,
            @LockMode = 'Exclusive',
            @LockOwner = 'Transaction',
            @LockTimeout = 5000;
        IF @lock_result < 0 THROW 51705, 'ASKLEGAL_APPROVAL_LOCK_FAILED', 1;

        IF EXISTS
        (
            SELECT 1 FROM register.command_v1_fact
            WHERE owning_application = 'PROMOTION_WORKER' AND command_id = @command_id
        )
        BEGIN
            EXEC register.resolve_command_v1
                @owning_application = 'PROMOTION_WORKER',
                @command_id = @command_id,
                @command_fingerprint = @command_fingerprint;
            COMMIT TRANSACTION;
            RETURN;
        END;

        IF NOT EXISTS
        (
            SELECT 1
            FROM review.proposal_package_review_v1 p WITH (HOLDLOCK)
            WHERE p.proposal_package_id = @proposal_package_id
              AND p.review_version = 1
              AND p.decision_event_type = 'PROPOSAL_APPROVED'
              AND p.decision_fingerprint = @decision_fingerprint
              AND JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.approval_id') =
                  @approval_id
              AND JSON_VALUE(
                    CONVERT(varchar(max), p.decision_bytes),
                    '$.promotion_manifest_ref.ref_id'
                  ) = @manifest_id
              AND JSON_VALUE(
                    CONVERT(varchar(max), p.decision_bytes),
                    '$.promotion_manifest_ref.fingerprint'
                  ) = @manifest_fingerprint
        )
            THROW 51706, 'ASKLEGAL_APPROVAL_NOT_INVALIDATABLE', 1;

        IF EXISTS
        (
            SELECT 1 FROM register.event_v1_fact WITH (UPDLOCK, HOLDLOCK)
            WHERE
                (owning_application = 'REVIEW_APPLICATION'
                 AND aggregate_id = @proposal_package_id
                 AND event_type IN ('APPROVAL_REVOKED', 'APPROVAL_INVALIDATED'))
                OR
                (owning_application = 'PROMOTION_WORKER'
                 AND aggregate_id = @approval_id
                 AND event_type IN ('APPROVAL_CONSUMED', 'APPROVAL_INVALIDATED'))
        )
            THROW 51706, 'ASKLEGAL_APPROVAL_NOT_INVALIDATABLE', 1;

        EXEC register.commit_command_v1
            @owning_application = 'PROMOTION_WORKER',
            @command_id = @command_id,
            @command_fingerprint = @command_fingerprint,
            @command_bytes = @command_bytes,
            @target_id = @approval_id,
            @expected_version = NULL,
            @expected_absent = 1,
            @expires_at = @expires_at,
            @guard_result_code = 'APPLIED',
            @winner_key = @winner_key,
            @event_id = @event_id,
            @event_type = 'APPROVAL_INVALIDATED',
            @event_bytes = @event_bytes,
            @event_fingerprint = @event_fingerprint;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;

GRANT EXECUTE ON OBJECT::promotion.invalidate_registered_approval_v1
    TO asklegal_promotion_role;
