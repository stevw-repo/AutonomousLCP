CREATE PROCEDURE register.read_claimed_effect_v1
    @effect_intent_id varchar(80),
    @claimant_id varchar(80),
    @fencing_token bigint
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

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
    DECLARE @owner varchar(48);
    SELECT @owner = owning_application
    FROM register.effect_intent_fact
    WHERE effect_intent_id = @effect_intent_id;

    IF @owner IS NULL
        THROW 51920, 'ASKLEGAL_EFFECT_INTENT_NOT_FOUND', 1;
    IF @caller_application IS NULL OR
       (@caller_application <> 'DBO' AND @caller_application <> @owner)
        THROW 51921, 'ASKLEGAL_EFFECT_OWNER_MISMATCH', 1;
    IF NOT EXISTS
    (
        SELECT 1
        FROM register.effect_claim_current
        WHERE effect_intent_id = @effect_intent_id
          AND claimant_id = @claimant_id
          AND fencing_token = @fencing_token
          AND expires_at > SYSUTCDATETIME()
    )
        THROW 51922, 'ASKLEGAL_STALE_FENCING_TOKEN', 1;
    IF EXISTS
    (
        SELECT 1
        FROM register.effect_receipt_fact
        WHERE effect_intent_id = @effect_intent_id
    )
        THROW 51923, 'ASKLEGAL_EFFECT_ALREADY_TERMINAL', 1;

    SELECT
        intent.effect_intent_id,
        intent.effect_type,
        intent.aggregate_id,
        intent.intent_bytes,
        intent.intent_fingerprint,
        intent.attempt_ceiling,
        (
            SELECT COUNT(*)
            FROM register.effect_attempt_fact attempt
            WHERE attempt.effect_intent_id = intent.effect_intent_id
        ) AS prior_attempt_count
    FROM register.effect_intent_fact intent
    WHERE intent.effect_intent_id = @effect_intent_id
      AND intent.owning_application = @owner;
END;
