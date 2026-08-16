CREATE PROCEDURE register.claim_effect_v1
    @effect_intent_id varchar(80),
    @claimant_id varchar(80),
    @lease_seconds int
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    IF @lease_seconds < 1 THROW 51220, 'ASKLEGAL_EFFECT_LEASE_INVALID', 1;

    DECLARE @now datetime2(7) = SYSUTCDATETIME();
    DECLARE @owner varchar(48);
    DECLARE @deadline datetime2(7);
    DECLARE @caller_application varchar(48) =
        CASE USER_NAME()
            WHEN 'asklegal_control_app' THEN 'CONTROL_PLANE'
            WHEN 'asklegal_review_app' THEN 'REVIEW_APPLICATION'
            WHEN 'asklegal_acquisition_app' THEN 'ACQUISITION_WORKER'
            WHEN 'asklegal_legal_processing_app' THEN 'LEGAL_PROCESSING_WORKER'
            WHEN 'asklegal_promotion_app' THEN 'PROMOTION_WORKER'
            WHEN 'dbo' THEN 'DBO'
            ELSE NULL
        END;

    BEGIN TRANSACTION;
    BEGIN TRY
        SELECT @owner = owning_application, @deadline = deadline
        FROM register.effect_intent_fact WITH (UPDLOCK, HOLDLOCK)
        WHERE effect_intent_id = @effect_intent_id;
        IF @owner IS NULL THROW 51221, 'ASKLEGAL_EFFECT_INTENT_NOT_FOUND', 1;
        IF @caller_application <> 'DBO' AND @caller_application <> @owner
            THROW 51222, 'ASKLEGAL_EFFECT_OWNER_MISMATCH', 1;
        IF @now >= @deadline THROW 51223, 'ASKLEGAL_EFFECT_DEADLINE_PASSED', 1;
        IF EXISTS (SELECT 1 FROM register.effect_receipt_fact
                   WHERE effect_intent_id = @effect_intent_id)
            THROW 51224, 'ASKLEGAL_EFFECT_ALREADY_TERMINAL', 1;

        IF EXISTS
        (
            SELECT 1 FROM register.effect_claim_current WITH (UPDLOCK, HOLDLOCK)
            WHERE effect_intent_id = @effect_intent_id AND expires_at > @now
        )
        BEGIN
            IF EXISTS
            (
                SELECT 1 FROM register.effect_claim_current
                WHERE effect_intent_id = @effect_intent_id AND claimant_id = @claimant_id
            )
            BEGIN
                SELECT effect_intent_id, claimant_id, generation, fencing_token,
                       claimed_at, expires_at
                FROM register.effect_claim_current WHERE effect_intent_id = @effect_intent_id;
                COMMIT TRANSACTION;
                RETURN;
            END;
            THROW 51225, 'ASKLEGAL_EFFECT_ALREADY_CLAIMED', 1;
        END;

        IF EXISTS (SELECT 1 FROM register.effect_claim_current
                   WHERE effect_intent_id = @effect_intent_id)
            UPDATE register.effect_claim_current
            SET claimant_id = @claimant_id,
                generation = generation + 1,
                fencing_token = fencing_token + 1,
                claimed_at = @now,
                expires_at = DATEADD(second, @lease_seconds, @now)
            WHERE effect_intent_id = @effect_intent_id;
        ELSE
            INSERT register.effect_claim_current
                (effect_intent_id, claimant_id, generation, fencing_token,
                 claimed_at, expires_at)
            VALUES
                (@effect_intent_id, @claimant_id, 1, 1,
                 @now, DATEADD(second, @lease_seconds, @now));

        SELECT effect_intent_id, claimant_id, generation, fencing_token,
               claimed_at, expires_at
        FROM register.effect_claim_current WHERE effect_intent_id = @effect_intent_id;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
