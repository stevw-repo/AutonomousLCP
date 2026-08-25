CREATE PROCEDURE promotion.begin_registered_execution_v1
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
    @action_id varchar(80),
    @action_fingerprint varchar(71),
    @capability_profile_id varchar(80),
    @capability_profile_fingerprint varchar(71),
    @capability_evidence_id varchar(80),
    @capability_evidence_fingerprint varchar(71),
    @expires_at datetime2(7),
    @event_id varchar(80),
    @event_bytes varbinary(max),
    @event_fingerprint binary(32),
    @effect_intent_id varchar(80),
    @effect_type varchar(48),
    @intent_bytes varbinary(max),
    @intent_fingerprint binary(32),
    @effect_deadline datetime2(7),
    @attempt_ceiling int
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

    DECLARE @decision_fingerprint_text varchar(71) =
        CONCAT('sha256:', LOWER(CONVERT(varchar(64), @decision_fingerprint, 2)));
    DECLARE @command_fingerprint_text varchar(71) =
        CONCAT('sha256:', LOWER(CONVERT(varchar(64), @command_fingerprint, 2)));
    DECLARE @command_json varchar(max) = CONVERT(varchar(max), @command_bytes);
    DECLARE @event_json varchar(max) = CONVERT(varchar(max), @event_bytes);
    DECLARE @intent_json varchar(max) = CONVERT(varchar(max), @intent_bytes);
    DECLARE @action_json varchar(max) = CONVERT(
        varchar(max), JSON_QUERY(@command_json, '$.action_authority')
    );

    IF HASHBYTES('SHA2_256', @command_bytes) <> @command_fingerprint
        THROW 51900, 'ASKLEGAL_COMMAND_BYTES_FINGERPRINT_MISMATCH', 1;
    IF HASHBYTES('SHA2_256', @event_bytes) <> @event_fingerprint
        THROW 51901, 'ASKLEGAL_EVENT_BYTES_FINGERPRINT_MISMATCH', 1;
    IF HASHBYTES('SHA2_256', @intent_bytes) <> @intent_fingerprint
        THROW 51902, 'ASKLEGAL_INTENT_BYTES_FINGERPRINT_MISMATCH', 1;

    -- Immutable command identity alone resolves a committed acknowledgement loss.
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
       RIGHT(@execution_lineage_id, 48) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       LEN(@event_id) <> 52 OR LEFT(@event_id, 4) <> 'pex_' OR
       RIGHT(@event_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       LEN(@effect_intent_id) <> 52 OR LEFT(@effect_intent_id, 4) <> 'efi_' OR
       RIGHT(@effect_intent_id, 48) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       LEN(@capability_profile_id) <> 52 OR LEFT(@capability_profile_id, 4) <> 'cap_' OR
       RIGHT(@capability_profile_id, 48) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       LEN(@capability_evidence_id) <> 52 OR LEFT(@capability_evidence_id, 4) <> 'evi_' OR
       RIGHT(@capability_evidence_id, 48) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       @action_id = '' OR
       @action_id COLLATE Latin1_General_100_BIN2 LIKE '%[^A-Z0-9_]%' OR
       LEFT(@action_id, 1) COLLATE Latin1_General_100_BIN2 LIKE '[^A-Z]' OR
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
           LIKE '%[^0-9a-f]%' OR
       LEN(@action_fingerprint) <> 71 OR LEFT(@action_fingerprint, 7) <> 'sha256:' OR
       RIGHT(@action_fingerprint, 64) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       LEN(@capability_profile_fingerprint) <> 71 OR
       LEFT(@capability_profile_fingerprint, 7) <> 'sha256:' OR
       RIGHT(@capability_profile_fingerprint, 64) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       LEN(@capability_evidence_fingerprint) <> 71 OR
       LEFT(@capability_evidence_fingerprint, 7) <> 'sha256:' OR
       RIGHT(@capability_evidence_fingerprint, 64) COLLATE Latin1_General_100_BIN2
           LIKE '%[^0-9a-f]%' OR
       @attempt_ceiling < 1
        THROW 51903, 'ASKLEGAL_EXECUTION_BEGIN_IDENTITY_INVALID', 1;

    IF ISJSON(@command_json) <> 1 OR
       (SELECT COUNT(*) FROM OPENJSON(@command_json)) <> 15 OR
       ISNULL(JSON_VALUE(@command_json, '$.action'), '') <>
           'BEGIN_REGISTERED_PROMOTION_EXECUTION' OR
       ISNULL(JSON_VALUE(@command_json, '$.action_contract_version'), '') <> '1.0.0' OR
       ISNULL(JSON_VALUE(@command_json, '$.action_fingerprint'), '') <>
           @action_fingerprint OR
       ISNULL(JSON_VALUE(@command_json, '$.approval_id'), '') <> @approval_id OR
       ISNULL(JSON_VALUE(@command_json, '$.authorization_fingerprint'), '') <>
           @authorization_fingerprint OR
       ISNULL(JSON_VALUE(@command_json, '$.effect_intent_id'), '') <> @effect_intent_id OR
       ISNULL(JSON_VALUE(@command_json, '$.execution_lineage_id'), '') <>
           @execution_lineage_id OR
       ISNULL(JSON_VALUE(@command_json, '$.execution_lineage_fingerprint'), '') <>
           @execution_lineage_fingerprint OR
       ISNULL(JSON_VALUE(@command_json, '$.manifest_id'), '') <> @manifest_id OR
       ISNULL(JSON_VALUE(@command_json, '$.manifest_fingerprint'), '') <>
           @manifest_fingerprint OR
       ISNULL(JSON_VALUE(@command_json, '$.proposal_package_id'), '') <>
           @proposal_package_id OR
       LEN(ISNULL(JSON_VALUE(@command_json, '$.promotion_worker_identity_id'), '')) <> 52 OR
       LEFT(ISNULL(JSON_VALUE(@command_json, '$.promotion_worker_identity_id'), ''), 4) <>
           'act_' OR
       RIGHT(ISNULL(JSON_VALUE(@command_json, '$.promotion_worker_identity_id'), ''), 48)
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
       ISNULL(JSON_VALUE(@command_json, '$.capability_evidence_ref.ref_type'), '') <>
           'EVIDENCE' OR
       ISNULL(JSON_VALUE(@command_json, '$.capability_evidence_ref.ref_id'), '') <>
           @capability_evidence_id OR
       ISNULL(JSON_VALUE(@command_json, '$.capability_evidence_ref.fingerprint'), '') <>
           @capability_evidence_fingerprint OR
       (SELECT COUNT(*) FROM OPENJSON(@command_json, '$.capability_evidence_ref')) <> 3
        THROW 51904, 'ASKLEGAL_EXECUTION_BEGIN_COMMAND_INVALID', 1;

    IF ISJSON(@action_json) <> 1 OR
       (SELECT COUNT(*) FROM OPENJSON(@action_json)) <> 18 OR
       ISNULL(TRY_CONVERT(int, JSON_VALUE(@action_json, '$.sequence')), -1) <> 1 OR
       ISNULL(JSON_VALUE(@action_json, '$.action_id'), '') <> @action_id OR
       ISNULL(JSON_VALUE(@action_json, '$.effect_type'), '') <> @effect_type OR
       ISNULL(JSON_VALUE(@action_json, '$.owning_application'), '') <>
           'PROMOTION_WORKER' OR
       ISNULL(JSON_VALUE(@action_json, '$.capability_profile_ref.ref_type'), '') <>
           'CAPABILITY_PROFILE' OR
       ISNULL(JSON_VALUE(@action_json, '$.capability_profile_ref.ref_id'), '') <>
           @capability_profile_id OR
       ISNULL(JSON_VALUE(@action_json, '$.capability_profile_ref.fingerprint'), '') <>
           @capability_profile_fingerprint OR
       (SELECT COUNT(*) FROM OPENJSON(@action_json, '$.capability_profile_ref')) <> 3 OR
       ISNULL(TRY_CONVERT(int, JSON_VALUE(@action_json, '$.attempt_ceiling')), -1) <>
           @attempt_ceiling OR
       TRY_CONVERT(datetimeoffset(7), JSON_VALUE(@action_json, '$.deadline'), 127) <>
           TODATETIMEOFFSET(@effect_deadline, '+00:00') OR
       CONCAT('sha256:', LOWER(CONVERT(varchar(64), HASHBYTES(
           'SHA2_256', CONVERT(varbinary(max), @action_json)
       ), 2))) <> @action_fingerprint OR
       TODATETIMEOFFSET(@expires_at, '+00:00') >
           TODATETIMEOFFSET(@effect_deadline, '+00:00')
        THROW 51905, 'ASKLEGAL_EXECUTION_BEGIN_ACTION_INVALID', 1;

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
       ISNULL(JSON_VALUE(@event_json, '$.from_state'), '') <> 'EXECUTION_AUTHORIZED' OR
       ISNULL(JSON_VALUE(@event_json, '$.to_state'), '') <> 'EXECUTION_RUNNING' OR
       ISNULL(JSON_VALUE(@event_json, '$.action_id'), '') <> 'BEGIN' OR
       ISNULL(TRY_CONVERT(int, JSON_VALUE(@event_json, '$.attempt_number')), -1) <> 0 OR
       ISNULL(JSON_VALUE(@event_json, '$.idempotency.idempotency_key'), '') <>
           CONCAT('begin:', @execution_lineage_id) OR
       ISNULL(JSON_VALUE(@event_json, '$.idempotency.input_fingerprint'), '') <>
           @command_fingerprint_text OR
       (SELECT COUNT(*) FROM OPENJSON(@event_json, '$.idempotency')) <> 2 OR
       ISNULL(JSON_VALUE(@event_json, '$.result_code'), '') <> 'SUCCEEDED' OR
       ISNULL(JSON_QUERY(@event_json, '$.failure_codes'), '') <> '[]' OR
       ISNULL(JSON_QUERY(@event_json, '$.reason_codes'), '') <>
           '["APPROVAL_EXACTLY_BOUND","REFERENCE_VERIFIED","TRANSITION_ALLOWED",'
           + '"VALIDATION_COMPLETE"]' OR
       ISNULL(JSON_QUERY(@event_json, '$.receipt_refs'), '') <> '[]' OR
       ISNULL(JSON_VALUE(@event_json, '$.external_effects'), '') <>
           'DECLARED_MANIFEST_ACTION' OR
       ISNULL(JSON_VALUE(@event_json, '$.immutable'), '') <> 'true' OR
       TRY_CONVERT(datetimeoffset(7), JSON_VALUE(@event_json, '$.event_time'), 127) IS NULL OR
       TRY_CONVERT(datetimeoffset(7), JSON_VALUE(@event_json, '$.event_time'), 127) >=
           TODATETIMEOFFSET(@expires_at, '+00:00')
        THROW 51906, 'ASKLEGAL_EXECUTION_BEGIN_EVENT_INVALID', 1;

    IF ISJSON(@intent_json) <> 1 OR
       (SELECT COUNT(*) FROM OPENJSON(@intent_json)) <> 24 OR
       ISNULL(JSON_VALUE(@intent_json, '$.schema_id'), '') <> 'asklegal.effect-intent' OR
       ISNULL(JSON_VALUE(@intent_json, '$.schema_version'), '') <> '1.0.0' OR
       ISNULL(JSON_VALUE(@intent_json, '$.effect_intent_id'), '') <> @effect_intent_id OR
       ISNULL(JSON_VALUE(@intent_json, '$.effect_type'), '') <> @effect_type OR
       ISNULL(JSON_VALUE(@intent_json, '$.owning_application'), '') <>
           'PROMOTION_WORKER' OR
       ISNULL(JSON_VALUE(@intent_json, '$.aggregate_ref.ref_type'), '') <>
           'EXECUTION_LINEAGE' OR
       ISNULL(JSON_VALUE(@intent_json, '$.aggregate_ref.ref_id'), '') <>
           @execution_lineage_id OR
       ISNULL(JSON_VALUE(@intent_json, '$.aggregate_ref.fingerprint'), '') <>
           @execution_lineage_fingerprint OR
       (SELECT COUNT(*) FROM OPENJSON(@intent_json, '$.aggregate_ref')) <> 3 OR
       ISNULL(JSON_VALUE(@intent_json, '$.execution_lineage_ref.ref_type'), '') <>
           'EXECUTION_LINEAGE' OR
       ISNULL(JSON_VALUE(@intent_json, '$.execution_lineage_ref.ref_id'), '') <>
           @execution_lineage_id OR
       ISNULL(JSON_VALUE(@intent_json, '$.execution_lineage_ref.fingerprint'), '') <>
           @execution_lineage_fingerprint OR
       (SELECT COUNT(*) FROM OPENJSON(@intent_json, '$.execution_lineage_ref')) <> 3 OR
       ISNULL(JSON_VALUE(@intent_json, '$.command_ref.ref_type'), '') <> 'COMMAND' OR
       ISNULL(JSON_VALUE(@intent_json, '$.command_ref.ref_id'), '') <> @command_id OR
       ISNULL(JSON_VALUE(@intent_json, '$.command_ref.fingerprint'), '') <>
           @command_fingerprint_text OR
       (SELECT COUNT(*) FROM OPENJSON(@intent_json, '$.command_ref')) <> 3 OR
       ISNULL(JSON_VALUE(@intent_json, '$.capability_profile_ref.ref_type'), '') <>
           'CAPABILITY_PROFILE' OR
       ISNULL(JSON_VALUE(@intent_json, '$.capability_profile_ref.ref_id'), '') <>
           @capability_profile_id OR
       ISNULL(JSON_VALUE(@intent_json, '$.capability_profile_ref.fingerprint'), '') <>
           @capability_profile_fingerprint OR
       (SELECT COUNT(*) FROM OPENJSON(@intent_json, '$.capability_profile_ref')) <> 3 OR
       ISNULL(JSON_VALUE(@intent_json, '$.permitted_checkpoint'), '') <>
           ISNULL(JSON_VALUE(@action_json, '$.permitted_checkpoint'), '') OR
       ISNULL(JSON_QUERY(@intent_json, '$.input_refs'), '') <>
           ISNULL(JSON_QUERY(@action_json, '$.input_refs'), '') OR
       ISNULL(JSON_VALUE(@intent_json, '$.effect_command_fingerprint'), '') <>
           ISNULL(JSON_VALUE(@action_json, '$.effect_command_fingerprint'), '') OR
       ISNULL(JSON_VALUE(@intent_json, '$.required_capability'), '') <>
           ISNULL(JSON_VALUE(@action_json, '$.required_capability'), '') OR
       ISNULL(JSON_VALUE(@intent_json, '$.destination_class'), '') <>
           ISNULL(JSON_VALUE(@action_json, '$.destination_class'), '') OR
       ISNULL(JSON_VALUE(@intent_json, '$.stable_idempotency_key'), '') <>
           ISNULL(JSON_VALUE(@action_json, '$.stable_idempotency_key'), '') OR
       ISNULL(JSON_VALUE(@intent_json, '$.retry_class'), '') <>
           ISNULL(JSON_VALUE(@action_json, '$.retry_class'), '') OR
       ISNULL(TRY_CONVERT(int, JSON_VALUE(@intent_json, '$.attempt_ceiling')), -1) <>
           @attempt_ceiling OR
       TRY_CONVERT(datetimeoffset(7), JSON_VALUE(@intent_json, '$.deadline'), 127) <>
           TODATETIMEOFFSET(@effect_deadline, '+00:00') OR
       ISNULL(JSON_QUERY(@intent_json, '$.stop_conditions'), '') <>
           ISNULL(JSON_QUERY(@action_json, '$.stop_conditions'), '') OR
       ISNULL(JSON_QUERY(@intent_json, '$.expected_remote_precondition_ref'), '') <>
           ISNULL(JSON_QUERY(@action_json, '$.expected_remote_precondition_ref'), '') OR
       ISNULL(JSON_QUERY(@intent_json, '$.success_postcondition_ref'), '') <>
           ISNULL(JSON_QUERY(@action_json, '$.success_postcondition_ref'), '') OR
       ISNULL(JSON_QUERY(@intent_json, '$.compensation'), '') <>
           ISNULL(JSON_QUERY(@action_json, '$.compensation'), '') OR
       ISNULL(JSON_VALUE(@intent_json, '$.created_at'), '') <>
           ISNULL(JSON_VALUE(@event_json, '$.event_time'), '') OR
       ISNULL(JSON_VALUE(@intent_json, '$.immutable'), '') <> 'true'
        THROW 51907, 'ASKLEGAL_EXECUTION_BEGIN_INTENT_INVALID', 1;

    DECLARE @lock_result int;
    DECLARE @lock_resource nvarchar(255) =
        CONCAT('asklegal:promotion-execution:', @execution_lineage_id);

    BEGIN TRANSACTION;
    BEGIN TRY
        EXEC @lock_result = sys.sp_getapplock
            @Resource = @lock_resource,
            @LockMode = 'Exclusive',
            @LockOwner = 'Transaction',
            @LockTimeout = 5000;
        IF @lock_result < 0 THROW 51908, 'ASKLEGAL_EXECUTION_BEGIN_LOCK_FAILED', 1;

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
            FROM register.event_v1_fact authorized WITH (UPDLOCK, HOLDLOCK)
            INNER JOIN register.command_v1_fact authorization_command WITH (HOLDLOCK)
                ON authorization_command.owning_application = authorized.owning_application
               AND authorization_command.command_id = authorized.command_id
            WHERE authorized.owning_application = 'PROMOTION_WORKER'
              AND authorized.aggregate_id = @execution_lineage_id
              AND authorized.event_type = 'PROMOTION_EXECUTION_AUTHORIZED'
              AND authorized.prior_version = 0
              AND authorized.new_version = 1
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes), '$.action'
                  ), '') = 'AUTHORIZE_REGISTERED_PROMOTION_EXECUTION'
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes), '$.approval_id'
                  ), '') = @approval_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.proposal_package_id'
                  ), '') = @proposal_package_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.decision_fingerprint'
                  ), '') = @decision_fingerprint_text
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes), '$.manifest_id'
                  ), '') = @manifest_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.manifest_fingerprint'
                  ), '') = @manifest_fingerprint
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.execution_lineage_id'
                  ), '') = @execution_lineage_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.execution_lineage_fingerprint'
                  ), '') = @execution_lineage_fingerprint
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.authorization_fingerprint'
                  ), '') = @authorization_fingerprint
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.promotion_worker_identity_id'
                  ), '') = JSON_VALUE(@command_json, '$.promotion_worker_identity_id')
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorization_command.command_bytes),
                    '$.promotion_worker_identity_fingerprint'
                  ), '') = JSON_VALUE(
                    @command_json, '$.promotion_worker_identity_fingerprint'
                  )
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorized.event_bytes), '$.from_state'
                  ), '') = 'EXECUTION_PLANNED'
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorized.event_bytes), '$.to_state'
                  ), '') = 'EXECUTION_AUTHORIZED'
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorized.event_bytes),
                    '$.promotion_manifest_ref.ref_id'
                  ), '') = @manifest_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorized.event_bytes),
                    '$.promotion_manifest_ref.fingerprint'
                  ), '') = @manifest_fingerprint
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorized.event_bytes), '$.approval_ref.ref_id'
                  ), '') = @approval_id
              AND ISNULL(JSON_VALUE(
                    CONVERT(varchar(max), authorized.event_bytes),
                    '$.approval_ref.fingerprint'
                  ), '') = @decision_fingerprint_text
        )
            THROW 51909, 'ASKLEGAL_AUTHORIZED_EXECUTION_NOT_BEGINNABLE', 1;

        EXEC register.commit_command_v1
            @owning_application = 'PROMOTION_WORKER',
            @command_id = @command_id,
            @command_fingerprint = @command_fingerprint,
            @command_bytes = @command_bytes,
            @target_id = @execution_lineage_id,
            @expected_version = 1,
            @expected_absent = 0,
            @expires_at = @expires_at,
            @guard_result_code = 'APPLIED',
            @winner_key = NULL,
            @event_id = @event_id,
            @event_type = 'PROMOTION_EXECUTION_BEGAN',
            @event_bytes = @event_bytes,
            @event_fingerprint = @event_fingerprint,
            @effect_intent_id = @effect_intent_id,
            @effect_type = @effect_type,
            @intent_bytes = @intent_bytes,
            @intent_fingerprint = @intent_fingerprint,
            @effect_deadline = @effect_deadline,
            @attempt_ceiling = @attempt_ceiling;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;

GRANT EXECUTE ON OBJECT::promotion.begin_registered_execution_v1
    TO asklegal_promotion_role;
