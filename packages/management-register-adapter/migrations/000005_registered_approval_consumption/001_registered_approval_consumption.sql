CREATE PROCEDURE promotion.consume_registered_approval_v1
    @command_id varchar(80),
    @command_fingerprint binary(32),
    @command_bytes varbinary(max),
    @approval_id varchar(80),
    @proposal_package_id varchar(80),
    @decision_fingerprint binary(32),
    @manifest_id varchar(80),
    @manifest_fingerprint varchar(71),
    @execution_lineage_id varchar(80),
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

    IF HASHBYTES('SHA2_256', @command_bytes) <> @command_fingerprint
        THROW 51500, 'ASKLEGAL_COMMAND_BYTES_FINGERPRINT_MISMATCH', 1;
    IF HASHBYTES('SHA2_256', @event_bytes) <> @event_fingerprint
        THROW 51501, 'ASKLEGAL_EVENT_BYTES_FINGERPRINT_MISMATCH', 1;
    IF @approval_id NOT LIKE 'apr[_]%' OR @proposal_package_id NOT LIKE 'ppk[_]%' OR
       @manifest_id NOT LIKE 'pmn[_]%' OR @execution_lineage_id NOT LIKE 'exe[_]%' OR
       @event_id NOT LIKE 'ape[_]%' OR
       @manifest_fingerprint NOT LIKE 'sha256:%' OR LEN(@manifest_fingerprint) <> 71
        THROW 51502, 'ASKLEGAL_APPROVAL_CONSUMPTION_IDENTITY_INVALID', 1;
    IF ISJSON(CONVERT(varchar(max), @command_bytes)) <> 1 OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @command_bytes), '$.action'), '') <>
           'CONSUME_REGISTERED_APPROVAL' OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @command_bytes), '$.approval_id'), '') <>
           @approval_id OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @command_bytes), '$.proposal_package_id'), '') <>
           @proposal_package_id OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @command_bytes), '$.decision_fingerprint'), '') <>
           @decision_fingerprint_text OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @command_bytes), '$.manifest_id'), '') <>
           @manifest_id OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @command_bytes), '$.manifest_fingerprint'), '') <>
           @manifest_fingerprint OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @command_bytes), '$.execution_lineage_id'), '') <>
           @execution_lineage_id
        THROW 51503, 'ASKLEGAL_APPROVAL_CONSUMPTION_COMMAND_INVALID', 1;
    IF ISJSON(CONVERT(varchar(max), @event_bytes)) <> 1 OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.schema_id'), '') <>
           'asklegal.approval-lifecycle-event' OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.schema_version'), '') <>
           '1.1.0' OR
       ISNULL(
           JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.approval_lifecycle_event_id'),
           ''
       ) <>
           @event_id OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.approval_ref.ref_id'), '') <>
           @approval_id OR
       ISNULL(
           JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.approval_ref.fingerprint'),
           ''
       ) <>
           @decision_fingerprint_text OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.from_state'), '') <>
           'APPROVAL_APPROVED' OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.to_state'), '') <>
           'APPROVAL_CONSUMED' OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.event_type'), '') <>
           'CONSUME_FOR_ONE_EXECUTION_LINEAGE' OR
       ISNULL(
           JSON_VALUE(
               CONVERT(varchar(max), @event_bytes),
               '$.execution_lineage_refs[0].ref_id'
           ),
           ''
       ) <>
           @execution_lineage_id OR
       ISNULL(JSON_VALUE(CONVERT(varchar(max), @event_bytes), '$.immutable'), '') <> 'true'
        THROW 51504, 'ASKLEGAL_APPROVAL_CONSUMPTION_EVENT_INVALID', 1;

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
        IF @lock_result < 0 THROW 51505, 'ASKLEGAL_APPROVAL_LOCK_FAILED', 1;

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
            THROW 51506, 'ASKLEGAL_APPROVAL_NOT_CONSUMABLE', 1;

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
            THROW 51506, 'ASKLEGAL_APPROVAL_NOT_CONSUMABLE', 1;

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
            @event_type = 'APPROVAL_CONSUMED',
            @event_bytes = @event_bytes,
            @event_fingerprint = @event_fingerprint;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;

GRANT EXECUTE ON OBJECT::promotion.consume_registered_approval_v1
    TO asklegal_promotion_role;
DENY EXECUTE ON OBJECT::register.commit_command_v1 TO asklegal_promotion_role;
