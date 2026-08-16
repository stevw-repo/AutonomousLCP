CREATE PROCEDURE register.commit_command_v1
    @owning_application varchar(48),
    @command_id varchar(80),
    @command_fingerprint binary(32),
    @command_bytes varbinary(max),
    @target_id varchar(80),
    @expected_version bigint = NULL,
    @expected_absent bit,
    @expires_at datetime2(7),
    @guard_result_code varchar(48),
    @winner_key varchar(160) = NULL,
    @event_id varchar(80) = NULL,
    @event_type varchar(80) = NULL,
    @event_bytes varbinary(max) = NULL,
    @event_fingerprint binary(32) = NULL,
    @effect_intent_id varchar(80) = NULL,
    @effect_type varchar(48) = NULL,
    @intent_bytes varbinary(max) = NULL,
    @intent_fingerprint binary(32) = NULL,
    @effect_deadline datetime2(7) = NULL,
    @attempt_ceiling int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

    IF HASHBYTES('SHA2_256', @command_bytes) <> @command_fingerprint
        THROW 51200, 'ASKLEGAL_COMMAND_BYTES_FINGERPRINT_MISMATCH', 1;
    IF (@expected_absent = 1 AND @expected_version IS NOT NULL) OR
       (@expected_absent = 0 AND (@expected_version IS NULL OR @expected_version < 0))
        THROW 51201, 'ASKLEGAL_EXPECTED_VERSION_INVALID', 1;
    IF @guard_result_code NOT IN
       ('APPLIED', 'REJECTED_INVALID_STATE', 'REJECTED_INVALID_INPUT',
        'REJECTED_UNAUTHORIZED', 'REJECTED_CAPABILITY')
        THROW 51202, 'ASKLEGAL_GUARD_RESULT_INVALID', 1;
    IF @guard_result_code <> 'APPLIED' AND
       (@winner_key IS NOT NULL OR @event_id IS NOT NULL OR @effect_intent_id IS NOT NULL)
        THROW 51203, 'ASKLEGAL_REJECTED_COMMAND_HAS_FACTS', 1;
    IF @guard_result_code = 'APPLIED' AND
       (@event_id IS NULL OR @event_type IS NULL OR @event_bytes IS NULL OR
        @event_fingerprint IS NULL)
        THROW 51204, 'ASKLEGAL_APPLIED_COMMAND_EVENT_REQUIRED', 1;
    IF @event_bytes IS NOT NULL AND HASHBYTES('SHA2_256', @event_bytes) <> @event_fingerprint
        THROW 51205, 'ASKLEGAL_EVENT_BYTES_FINGERPRINT_MISMATCH', 1;
    IF @effect_intent_id IS NOT NULL AND
       (@effect_type IS NULL OR @intent_bytes IS NULL OR @intent_fingerprint IS NULL OR
        @effect_deadline IS NULL OR @attempt_ceiling IS NULL OR @attempt_ceiling < 1)
        THROW 51206, 'ASKLEGAL_EFFECT_INTENT_INCOMPLETE', 1;
    IF @intent_bytes IS NOT NULL AND HASHBYTES('SHA2_256', @intent_bytes) <> @intent_fingerprint
        THROW 51207, 'ASKLEGAL_INTENT_BYTES_FINGERPRINT_MISMATCH', 1;

    DECLARE @lock_result int;
    DECLARE @lock_resource nvarchar(255) =
        CONCAT('asklegal:aggregate:', @owning_application, ':', @target_id);
    DECLARE @current_version bigint;
    DECLARE @result_code varchar(48);
    DECLARE @new_version bigint;
    DECLARE @result_bytes varbinary(max);
    DECLARE @caller sysname = USER_NAME();
    DECLARE @caller_application varchar(48) =
        CASE @caller
            WHEN 'asklegal_control_app' THEN 'CONTROL_PLANE'
            WHEN 'asklegal_review_app' THEN 'REVIEW_APPLICATION'
            WHEN 'asklegal_acquisition_app' THEN 'ACQUISITION_WORKER'
            WHEN 'asklegal_legal_processing_app' THEN 'LEGAL_PROCESSING_WORKER'
            WHEN 'asklegal_promotion_app' THEN 'PROMOTION_WORKER'
            WHEN 'dbo' THEN @owning_application
            ELSE NULL
        END;

    BEGIN TRANSACTION;
    BEGIN TRY
        IF EXISTS
        (
            SELECT 1 FROM register.command_v1_fact
            WHERE owning_application = @owning_application AND command_id = @command_id
        )
        BEGIN
            IF EXISTS
            (
                SELECT 1 FROM register.command_v1_fact
                WHERE owning_application = @owning_application AND command_id = @command_id
                  AND command_fingerprint <> @command_fingerprint
            )
                THROW 51208, 'ASKLEGAL_COMMAND_FINGERPRINT_MISMATCH', 1;
            SELECT command_id, result_code, authoritative_version, result_bytes,
                   CAST(1 AS bit) AS replayed
            FROM register.command_v1_fact
            WHERE owning_application = @owning_application AND command_id = @command_id;
            COMMIT TRANSACTION;
            RETURN;
        END;

        EXEC @lock_result = sys.sp_getapplock
            @Resource = @lock_resource,
            @LockMode = 'Exclusive',
            @LockOwner = 'Transaction',
            @LockTimeout = 5000;
        IF @lock_result < 0 THROW 51209, 'ASKLEGAL_AGGREGATE_LOCK_FAILED', 1;

        SELECT @current_version = aggregate_version
        FROM register.aggregate_current WITH (UPDLOCK, HOLDLOCK)
        WHERE owning_application = @owning_application AND aggregate_id = @target_id;

        SET @result_code = @guard_result_code;
        IF @caller_application IS NULL OR @caller_application <> @owning_application
            SET @result_code = 'REJECTED_UNAUTHORIZED';
        ELSE IF SYSUTCDATETIME() >= @expires_at
            SET @result_code = 'REJECTED_EXPIRED';
        ELSE IF (@expected_absent = 1 AND @current_version IS NOT NULL) OR
                (@expected_absent = 0 AND
                 (@current_version IS NULL OR @current_version <> @expected_version))
            SET @result_code = 'REJECTED_STALE_VERSION';
        ELSE IF @winner_key IS NOT NULL AND EXISTS
                (SELECT 1 FROM register.single_winner_current WITH (UPDLOCK, HOLDLOCK)
                 WHERE winner_key = @winner_key)
            SET @result_code = 'REJECTED_CONFLICT';

        SET @new_version = @current_version;
        IF @result_code = 'APPLIED'
        BEGIN
            SET @new_version = ISNULL(@current_version, 0) + 1;
            IF @current_version IS NULL
                INSERT register.aggregate_current
                    (owning_application, aggregate_id, aggregate_version,
                     last_command_id, updated_at)
                VALUES
                    (@owning_application, @target_id, @new_version,
                     @command_id, SYSUTCDATETIME());
            ELSE
                UPDATE register.aggregate_current
                SET aggregate_version = @new_version,
                    last_command_id = @command_id,
                    updated_at = SYSUTCDATETIME()
                WHERE owning_application = @owning_application AND aggregate_id = @target_id;

            INSERT register.event_v1_fact
                (event_id, owning_application, command_id, aggregate_id, event_type,
                 prior_version, new_version, event_bytes, event_fingerprint, recorded_at)
            VALUES
                (@event_id, @owning_application, @command_id, @target_id, @event_type,
                 ISNULL(@current_version, 0), @new_version, @event_bytes,
                 @event_fingerprint, SYSUTCDATETIME());

            IF @winner_key IS NOT NULL
                INSERT register.single_winner_current(winner_key, command_id, recorded_at)
                VALUES (@winner_key, @command_id, SYSUTCDATETIME());

            IF @effect_intent_id IS NOT NULL
                INSERT register.effect_intent_fact
                    (effect_intent_id, owning_application, command_id, aggregate_id,
                     effect_type, intent_bytes, intent_fingerprint, deadline,
                     attempt_ceiling, recorded_at)
                VALUES
                    (@effect_intent_id, @owning_application, @command_id, @target_id,
                     @effect_type, @intent_bytes, @intent_fingerprint, @effect_deadline,
                     @attempt_ceiling, SYSUTCDATETIME());
        END;

        SET @result_bytes = CONVERT(varbinary(max), CONCAT(
            '{"authoritative_version":',
            CASE WHEN @new_version IS NULL THEN 'null' ELSE CONVERT(varchar(24), @new_version) END,
            ',"command_id":"', STRING_ESCAPE(@command_id, 'json'),
            '","result_code":"', @result_code, '"}'));

        INSERT register.command_v1_fact
            (owning_application, command_id, command_fingerprint, command_bytes,
             target_id, expected_version, expected_absent, result_code,
             authoritative_version, result_bytes, recorded_at)
        VALUES
            (@owning_application, @command_id, @command_fingerprint, @command_bytes,
             @target_id, @expected_version, @expected_absent, @result_code,
             @new_version, @result_bytes, SYSUTCDATETIME());

        SELECT @command_id, @result_code, @new_version, @result_bytes,
               CAST(0 AS bit) AS replayed;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
