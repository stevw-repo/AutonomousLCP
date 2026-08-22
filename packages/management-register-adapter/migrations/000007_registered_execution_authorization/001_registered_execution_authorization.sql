CREATE PROCEDURE promotion.authorize_registered_execution_v1
    @command_id varchar(80),
    @command_fingerprint binary(32),
    @command_bytes varbinary(max),
    @approval_id varchar(80),
    @proposal_package_id varchar(80),
    @decision_fingerprint binary(32),
    @manifest_id varchar(80),
    @manifest_fingerprint varchar(71),
    @execution_lineage_id varchar(80),
    @execution_lineage_fingerprint varchar(71),
    @authorization_fingerprint varchar(71),
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
        THROW 51800, 'ASKLEGAL_COMMAND_BYTES_FINGERPRINT_MISMATCH', 1;
    IF HASHBYTES('SHA2_256', @event_bytes) <> @event_fingerprint
        THROW 51801, 'ASKLEGAL_EVENT_BYTES_FINGERPRINT_MISMATCH', 1;

    -- Replay is resolved only by immutable command identity and fingerprint.
    -- Auxiliary procedure arguments have no authority over a committed result.
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

    IF LEN(@command_id) <> 52 OR LEFT(@command_id, 4) <> 'cmd_' OR
       RIGHT(@command_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(@approval_id) <> 52 OR LEFT(@approval_id, 4) <> 'apr_' OR
       RIGHT(@approval_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(@proposal_package_id) <> 52 OR LEFT(@proposal_package_id, 4) <> 'ppk_' OR
       RIGHT(@proposal_package_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(@manifest_id) <> 52 OR LEFT(@manifest_id, 4) <> 'pmn_' OR
       RIGHT(@manifest_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(@execution_lineage_id) <> 52 OR LEFT(@execution_lineage_id, 4) <> 'exe_' OR
       RIGHT(@execution_lineage_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(@event_id) <> 52 OR LEFT(@event_id, 4) <> 'pex_' OR
       RIGHT(@event_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(@manifest_fingerprint) <> 71 OR LEFT(@manifest_fingerprint, 7) <> 'sha256:' OR
       RIGHT(@manifest_fingerprint, 64) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       LEN(@execution_lineage_fingerprint) <> 71 OR
       LEFT(@execution_lineage_fingerprint, 7) <> 'sha256:' OR
       RIGHT(@execution_lineage_fingerprint, 64) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       LEN(@authorization_fingerprint) <> 71 OR
       LEFT(@authorization_fingerprint, 7) <> 'sha256:' OR
       RIGHT(@authorization_fingerprint, 64) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%'
        THROW 51802, 'ASKLEGAL_EXECUTION_AUTHORIZATION_IDENTITY_INVALID', 1;

    IF ISJSON(@command_json) <> 1 OR
       (SELECT COUNT(*) FROM OPENJSON(@command_json)) <> 13 OR
       ISNULL(JSON_VALUE(@command_json, '$.action'), '') <>
           'AUTHORIZE_REGISTERED_PROMOTION_EXECUTION' OR
       ISNULL(JSON_VALUE(@command_json, '$.approval_id'), '') <> @approval_id OR
       ISNULL(JSON_VALUE(@command_json, '$.proposal_package_id'), '') <>
           @proposal_package_id OR
       ISNULL(JSON_VALUE(@command_json, '$.decision_fingerprint'), '') <>
           @decision_fingerprint_text OR
       ISNULL(JSON_VALUE(@command_json, '$.manifest_id'), '') <> @manifest_id OR
       ISNULL(JSON_VALUE(@command_json, '$.manifest_fingerprint'), '') <>
           @manifest_fingerprint OR
       ISNULL(JSON_VALUE(@command_json, '$.execution_lineage_id'), '') <>
           @execution_lineage_id OR
       ISNULL(JSON_VALUE(@command_json, '$.execution_lineage_fingerprint'), '') <>
           @execution_lineage_fingerprint OR
       ISNULL(JSON_VALUE(@command_json, '$.authorization_fingerprint'), '') <>
           @authorization_fingerprint OR
       LEN(ISNULL(JSON_VALUE(@command_json, '$.promotion_worker_identity_id'), '')) <> 52 OR
       LEFT(ISNULL(JSON_VALUE(@command_json, '$.promotion_worker_identity_id'), ''), 4) <>
           'act_' OR
       RIGHT(ISNULL(JSON_VALUE(@command_json, '$.promotion_worker_identity_id'), ''), 48)
           COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(ISNULL(JSON_VALUE(@command_json, '$.validation_evidence_id'), '')) <> 52 OR
       LEFT(ISNULL(JSON_VALUE(@command_json, '$.validation_evidence_id'), ''), 4) <>
           'evi_' OR
       RIGHT(ISNULL(JSON_VALUE(@command_json, '$.validation_evidence_id'), ''), 48)
           COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(ISNULL(
           JSON_VALUE(@command_json, '$.promotion_worker_identity_fingerprint'), ''
       )) <> 71 OR
       LEFT(ISNULL(
           JSON_VALUE(@command_json, '$.promotion_worker_identity_fingerprint'), ''
       ), 7) <> 'sha256:' OR
       RIGHT(ISNULL(
           JSON_VALUE(@command_json, '$.promotion_worker_identity_fingerprint'), ''
       ), 64) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(ISNULL(
           JSON_VALUE(@command_json, '$.validation_evidence_fingerprint'), ''
       )) <> 71 OR
       LEFT(ISNULL(
           JSON_VALUE(@command_json, '$.validation_evidence_fingerprint'), ''
       ), 7) <> 'sha256:' OR
       RIGHT(ISNULL(
           JSON_VALUE(@command_json, '$.validation_evidence_fingerprint'), ''
       ), 64) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%'
        THROW 51803, 'ASKLEGAL_EXECUTION_AUTHORIZATION_COMMAND_INVALID', 1;

    DECLARE @expected_authorization_bytes varbinary(max) = CONVERT(
        varbinary(max),
        CONVERT(varchar(max), CONCAT(
            '{"approval_id":"', @approval_id,
            '","decision_fingerprint":"', @decision_fingerprint_text,
            '","execution_lineage_fingerprint":"', @execution_lineage_fingerprint,
            '","execution_lineage_id":"', @execution_lineage_id,
            '","manifest_fingerprint":"', @manifest_fingerprint,
            '","manifest_id":"', @manifest_id,
            '","promotion_worker_identity_fingerprint":"',
            JSON_VALUE(@command_json, '$.promotion_worker_identity_fingerprint'),
            '","promotion_worker_identity_id":"',
            JSON_VALUE(@command_json, '$.promotion_worker_identity_id'),
            '","proposal_package_id":"', @proposal_package_id,
            '","validation_evidence_fingerprint":"',
            JSON_VALUE(@command_json, '$.validation_evidence_fingerprint'),
            '","validation_evidence_id":"',
            JSON_VALUE(@command_json, '$.validation_evidence_id'), '"}'
        ))
    );
    DECLARE @expected_authorization_fingerprint varchar(71) = CONCAT(
        'sha256:', LOWER(CONVERT(
            varchar(64), HASHBYTES('SHA2_256', @expected_authorization_bytes), 2
        ))
    );
    IF @authorization_fingerprint <> @expected_authorization_fingerprint
        THROW 51803, 'ASKLEGAL_EXECUTION_AUTHORIZATION_COMMAND_INVALID', 1;

    IF ISJSON(@event_json) <> 1 OR
       (SELECT COUNT(*) FROM OPENJSON(@event_json)) <> 18 OR
       ISNULL(JSON_VALUE(@event_json, '$.schema_id'), '') <>
           'asklegal.promotion-execution-event' OR
       ISNULL(JSON_VALUE(@event_json, '$.schema_version'), '') <> '1.0.0' OR
       ISNULL(JSON_VALUE(@event_json, '$.promotion_execution_event_id'), '') <> @event_id OR
       ISNULL(JSON_VALUE(@event_json, '$.promotion_manifest_ref.ref_type'), '') <>
           'PROMOTION_MANIFEST' OR
       ISNULL(JSON_VALUE(@event_json, '$.promotion_manifest_ref.ref_id'), '') <>
           @manifest_id OR
       ISNULL(JSON_VALUE(@event_json, '$.promotion_manifest_ref.fingerprint'), '') <>
           @manifest_fingerprint OR
       (SELECT COUNT(*) FROM OPENJSON(@event_json, '$.promotion_manifest_ref')) <> 3 OR
       ISNULL(JSON_VALUE(@event_json, '$.approval_ref.ref_type'), '') <> 'APPROVAL' OR
       ISNULL(JSON_VALUE(@event_json, '$.approval_ref.ref_id'), '') <> @approval_id OR
       ISNULL(JSON_VALUE(@event_json, '$.approval_ref.fingerprint'), '') <>
           @decision_fingerprint_text OR
       (SELECT COUNT(*) FROM OPENJSON(@event_json, '$.approval_ref')) <> 3 OR
       ISNULL(JSON_VALUE(@event_json, '$.execution_lineage_id'), '') <>
           @execution_lineage_id OR
       ISNULL(JSON_VALUE(@event_json, '$.from_state'), '') <> 'EXECUTION_PLANNED' OR
       ISNULL(JSON_VALUE(@event_json, '$.to_state'), '') <> 'EXECUTION_AUTHORIZED' OR
       ISNULL(JSON_VALUE(@event_json, '$.action_id'), '') <> 'AUTHORIZE' OR
       ISNULL(TRY_CONVERT(int, JSON_VALUE(@event_json, '$.attempt_number')), -1) <> 0 OR
       ISNULL(JSON_VALUE(@event_json, '$.idempotency.idempotency_key'), '') <>
           CONCAT('authorize:', @execution_lineage_id) OR
       ISNULL(JSON_VALUE(@event_json, '$.idempotency.input_fingerprint'), '') <>
           @authorization_fingerprint OR
       (SELECT COUNT(*) FROM OPENJSON(@event_json, '$.idempotency')) <> 2 OR
       ISNULL(JSON_VALUE(@event_json, '$.result_code'), '') <> 'SUCCEEDED' OR
       ISNULL(JSON_QUERY(@event_json, '$.failure_codes'), '') <> '[]' OR
       ISNULL(JSON_QUERY(@event_json, '$.reason_codes'), '') <>
           '["APPROVAL_EXACTLY_BOUND","TRANSITION_ALLOWED","VALIDATION_COMPLETE"]' OR
       ISNULL(JSON_QUERY(@event_json, '$.receipt_refs'), '') <> '[]' OR
       ISNULL(JSON_VALUE(@event_json, '$.external_effects'), '') <> 'NONE' OR
       ISNULL(JSON_VALUE(@event_json, '$.immutable'), '') <> 'true' OR
       TRY_CONVERT(datetimeoffset(7), JSON_VALUE(@event_json, '$.event_time'), 127) IS NULL OR
       TRY_CONVERT(datetimeoffset(7), JSON_VALUE(@event_json, '$.event_time'), 127) >=
           TODATETIMEOFFSET(@expires_at, '+00:00')
        THROW 51804, 'ASKLEGAL_EXECUTION_AUTHORIZATION_EVENT_INVALID', 1;

    DECLARE @lock_result int;
    DECLARE @lock_resource nvarchar(255) =
        CONCAT('asklegal:promotion-execution:', @execution_lineage_id);
    DECLARE @winner_key varchar(160) =
        CONCAT('promotion-execution:', @execution_lineage_id);

    BEGIN TRANSACTION;
    BEGIN TRY
        EXEC @lock_result = sys.sp_getapplock
            @Resource = @lock_resource,
            @LockMode = 'Exclusive',
            @LockOwner = 'Transaction',
            @LockTimeout = 5000;
        IF @lock_result < 0 THROW 51805, 'ASKLEGAL_EXECUTION_AUTHORIZATION_LOCK_FAILED', 1;

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
            FROM register.event_v1_fact consumed WITH (UPDLOCK, HOLDLOCK)
            INNER JOIN register.command_v1_fact consumption_command WITH (HOLDLOCK)
                ON consumption_command.owning_application = consumed.owning_application
               AND consumption_command.command_id = consumed.command_id
            WHERE consumed.owning_application = 'PROMOTION_WORKER'
              AND consumed.aggregate_id = @approval_id
              AND consumed.event_type = 'APPROVAL_CONSUMED'
              AND consumed.new_version = 1
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumption_command.command_bytes),
                    '$.approval_id'
                  ), '') = @approval_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumption_command.command_bytes),
                    '$.proposal_package_id'
                  ), '') = @proposal_package_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumption_command.command_bytes),
                    '$.decision_fingerprint'
                  ), '') = @decision_fingerprint_text
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumption_command.command_bytes),
                    '$.manifest_id'
                  ), '') = @manifest_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumption_command.command_bytes),
                    '$.manifest_fingerprint'
                  ), '') = @manifest_fingerprint
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumption_command.command_bytes),
                    '$.execution_lineage_id'
                  ), '') = @execution_lineage_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.approval_ref.ref_id'
                  ), '') = @approval_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.approval_ref.fingerprint'
                  ), '') = @decision_fingerprint_text
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.execution_lineage_refs[0].ref_type'
                  ), '') = 'EXECUTION_LINEAGE'
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.execution_lineage_refs[0].ref_id'
                  ), '') = @execution_lineage_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.execution_lineage_refs[0].fingerprint'
                  ), '') = @execution_lineage_fingerprint
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.responsible_identity_ref.ref_type'
                  ), '') = 'ACTOR'
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.responsible_identity_ref.ref_id'
                  ), '') = JSON_VALUE(@command_json, '$.promotion_worker_identity_id')
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.responsible_identity_ref.fingerprint'
                  ), '') = JSON_VALUE(
                    @command_json, '$.promotion_worker_identity_fingerprint'
                  )
              AND EXISTS
              (
                  SELECT 1
                  FROM OPENJSON(
                      CONVERT(varchar(max), consumed.event_bytes), '$.evidence_refs'
                  ) evidence
                  WHERE ISNULL(JSON_VALUE(evidence.value, '$.ref_type'), '') = 'EVIDENCE'
                    AND ISNULL(JSON_VALUE(evidence.value, '$.ref_id'), '') =
                        JSON_VALUE(@command_json, '$.validation_evidence_id')
                    AND ISNULL(JSON_VALUE(evidence.value, '$.fingerprint'), '') =
                        JSON_VALUE(@command_json, '$.validation_evidence_fingerprint')
              )
        )
            THROW 51806, 'ASKLEGAL_CONSUMED_APPROVAL_NOT_AUTHORIZABLE', 1;

        EXEC register.commit_command_v1
            @owning_application = 'PROMOTION_WORKER',
            @command_id = @command_id,
            @command_fingerprint = @command_fingerprint,
            @command_bytes = @command_bytes,
            @target_id = @execution_lineage_id,
            @expected_version = NULL,
            @expected_absent = 1,
            @expires_at = @expires_at,
            @guard_result_code = 'APPLIED',
            @winner_key = @winner_key,
            @event_id = @event_id,
            @event_type = 'PROMOTION_EXECUTION_AUTHORIZED',
            @event_bytes = @event_bytes,
            @event_fingerprint = @event_fingerprint;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;

GRANT EXECUTE ON OBJECT::promotion.authorize_registered_execution_v1
    TO asklegal_promotion_role;
