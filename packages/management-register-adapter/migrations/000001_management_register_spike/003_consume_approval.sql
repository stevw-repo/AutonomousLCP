CREATE PROCEDURE review.consume_approval
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

    DECLARE @result_bytes varbinary(max) = CONVERT(varbinary(max), '{"status":"consumed"}');
    DECLARE @lock_result int;
    DECLARE @lock_resource nvarchar(255) = CONCAT('asklegal:approval:', @approval_id);

    IF HASHBYTES('SHA2_256', @command_bytes) <> @command_fingerprint
        THROW 51002, 'ASKLEGAL_COMMAND_BYTES_FINGERPRINT_MISMATCH', 1;

    BEGIN TRANSACTION;
    BEGIN TRY
        EXEC @lock_result = sys.sp_getapplock
            @Resource = @lock_resource,
            @LockMode = 'Exclusive',
            @LockOwner = 'Transaction',
            @LockTimeout = 5000;
        IF @lock_result < 0
            THROW 51003, 'ASKLEGAL_APPROVAL_LOCK_FAILED', 1;

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
            FROM register.command_fact
            WHERE command_id = @command_id;
            COMMIT TRANSACTION;
            RETURN;
        END;

        UPDATE review.approval_current WITH (UPDLOCK, HOLDLOCK)
        SET state_code = 'CONSUMED',
            consumed_by_command_id = @command_id,
            updated_at = SYSUTCDATETIME()
        WHERE approval_id = @approval_id
          AND manifest_fingerprint = @manifest_fingerprint
          AND state_code = 'VALID';

        IF @@ROWCOUNT <> 1
            THROW 51004, 'ASKLEGAL_APPROVAL_NOT_VALID', 1;

        INSERT register.inbox_fact(command_id, command_fingerprint, claimed_at)
        VALUES (@command_id, @command_fingerprint, SYSUTCDATETIME());

        INSERT register.lifecycle_fact
            (event_id, object_type, object_id, lifecycle_code, command_id,
             payload_bytes, payload_fingerprint, recorded_at)
        VALUES
            (NEWID(), 'Approval', @approval_id, 'CONSUMED', @command_id,
             @command_bytes, @command_fingerprint, SYSUTCDATETIME());

        INSERT register.outbox_fact
            (intent_id, command_id, intent_type, intent_bytes, intent_fingerprint, recorded_at)
        VALUES
            (NEWID(), @command_id, 'ApprovalConsumed', @command_bytes,
             @command_fingerprint, SYSUTCDATETIME());

        INSERT register.command_fact
            (command_id, command_fingerprint, command_bytes, result_code, result_bytes, recorded_at)
        VALUES
            (@command_id, @command_fingerprint, @command_bytes,
             'APPROVAL_CONSUMED', @result_bytes, SYSUTCDATETIME());

        SELECT @command_id, 'APPROVAL_CONSUMED', @result_bytes, CAST(0 AS bit) AS replayed;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
