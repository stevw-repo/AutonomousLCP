CREATE PROCEDURE promotion.activate_serving_state
    @command_id varchar(80),
    @command_fingerprint binary(32),
    @approval_id varchar(80),
    @manifest_fingerprint binary(32),
    @command_bytes varbinary(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

    DECLARE @result_bytes varbinary(max) = CONVERT(varbinary(max), '{"status":"active"}');
    DECLARE @lock_result int;

    IF HASHBYTES('SHA2_256', @command_bytes) <> @command_fingerprint
        THROW 51002, 'ASKLEGAL_COMMAND_BYTES_FINGERPRINT_MISMATCH', 1;

    BEGIN TRANSACTION;
    BEGIN TRY
        EXEC @lock_result = sys.sp_getapplock
            @Resource = 'asklegal:serving-state:singleton',
            @LockMode = 'Exclusive',
            @LockOwner = 'Transaction',
            @LockTimeout = 5000;
        IF @lock_result < 0
            THROW 51005, 'ASKLEGAL_SERVING_LOCK_FAILED', 1;

        IF EXISTS (SELECT 1 FROM register.command_fact WHERE command_id = @command_id)
        BEGIN
            IF EXISTS
            (
                SELECT 1 FROM register.command_fact
                WHERE command_id = @command_id
                  AND command_fingerprint <> @command_fingerprint
            )
                THROW 51001, 'ASKLEGAL_COMMAND_FINGERPRINT_MISMATCH', 1;
            SELECT command_id, result_code, result_bytes, CAST(1 AS bit) AS replayed
            FROM register.command_fact WHERE command_id = @command_id;
            COMMIT TRANSACTION;
            RETURN;
        END;

        IF NOT EXISTS
        (
            SELECT 1 FROM review.approval_current
            WHERE approval_id = @approval_id
              AND manifest_fingerprint = @manifest_fingerprint
              AND state_code = 'CONSUMED'
        )
            THROW 51006, 'ASKLEGAL_CONSUMED_APPROVAL_REQUIRED', 1;

        DELETE FROM promotion.serving_state_current WHERE singleton_id = 1;
        INSERT promotion.serving_state_current
            (singleton_id, manifest_fingerprint, activation_command_id, updated_at)
        VALUES (1, @manifest_fingerprint, @command_id, SYSUTCDATETIME());

        INSERT register.inbox_fact VALUES
            (@command_id, @command_fingerprint, SYSUTCDATETIME());
        INSERT register.lifecycle_fact VALUES
            (NEWID(), 'ServingState', 'active', 'ACTIVATED', @command_id,
             @command_bytes, @command_fingerprint, SYSUTCDATETIME());
        INSERT register.outbox_fact VALUES
            (NEWID(), @command_id, 'ServingStateActivated', @command_bytes,
             @command_fingerprint, SYSUTCDATETIME());
        INSERT register.command_fact VALUES
            (@command_id, @command_fingerprint, @command_bytes,
             'SERVING_STATE_ACTIVATED', @result_bytes, SYSUTCDATETIME());

        SELECT @command_id, 'SERVING_STATE_ACTIVATED', @result_bytes, CAST(0 AS bit);
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
