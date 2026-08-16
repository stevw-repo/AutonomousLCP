CREATE PROCEDURE register.record_effect_receipt_v1
    @effect_receipt_id varchar(80),
    @effect_intent_id varchar(80),
    @terminal_status varchar(32),
    @attempt_count int,
    @receipt_bytes varbinary(max),
    @receipt_fingerprint binary(32),
    @claimant_id varchar(80) = NULL,
    @fencing_token bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    IF HASHBYTES('SHA2_256', @receipt_bytes) <> @receipt_fingerprint
        THROW 51229, 'ASKLEGAL_RECEIPT_BYTES_FINGERPRINT_MISMATCH', 1;

    BEGIN TRANSACTION;
    BEGIN TRY
        IF EXISTS (SELECT 1 FROM register.effect_receipt_fact WITH (UPDLOCK, HOLDLOCK)
                   WHERE effect_intent_id = @effect_intent_id)
        BEGIN
            IF EXISTS
            (
                SELECT 1 FROM register.effect_receipt_fact
                WHERE effect_intent_id = @effect_intent_id
                  AND receipt_fingerprint <> @receipt_fingerprint
            ) THROW 51230, 'ASKLEGAL_EFFECT_RECEIPT_CONFLICT', 1;
            SELECT effect_receipt_id, effect_intent_id, terminal_status,
                   attempt_count, receipt_bytes, fencing_token, CAST(1 AS bit) AS replayed
            FROM register.effect_receipt_fact WHERE effect_intent_id = @effect_intent_id;
            COMMIT TRANSACTION;
            RETURN;
        END;

        DECLARE @actual_attempt_count int =
            (SELECT COUNT(*) FROM register.effect_attempt_fact
             WHERE effect_intent_id = @effect_intent_id);
        IF @terminal_status = 'CANCELLED_BEFORE_EFFECT' AND @actual_attempt_count <> 0
            THROW 51231, 'ASKLEGAL_EFFECT_ALREADY_STARTED', 1;
        IF @attempt_count <> @actual_attempt_count
            THROW 51232, 'ASKLEGAL_EFFECT_ATTEMPT_COUNT_MISMATCH', 1;
        IF @terminal_status <> 'CANCELLED_BEFORE_EFFECT' AND NOT EXISTS
        (
            SELECT 1 FROM register.effect_claim_current
            WHERE effect_intent_id = @effect_intent_id
              AND claimant_id = @claimant_id
              AND fencing_token = @fencing_token
              AND expires_at > SYSUTCDATETIME()
        ) THROW 51227, 'ASKLEGAL_STALE_FENCING_TOKEN', 1;

        INSERT register.effect_receipt_fact
            (effect_receipt_id, effect_intent_id, terminal_status, attempt_count,
             receipt_bytes, receipt_fingerprint, fencing_token, recorded_at)
        VALUES
            (@effect_receipt_id, @effect_intent_id, @terminal_status, @attempt_count,
             @receipt_bytes, @receipt_fingerprint, @fencing_token, SYSUTCDATETIME());
        SELECT @effect_receipt_id, @effect_intent_id, @terminal_status,
               @attempt_count, @receipt_bytes, @fencing_token, CAST(0 AS bit) AS replayed;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
