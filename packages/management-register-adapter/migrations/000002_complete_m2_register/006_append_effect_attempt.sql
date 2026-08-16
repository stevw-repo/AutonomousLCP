CREATE PROCEDURE register.append_effect_attempt_v1
    @effect_intent_id varchar(80),
    @claimant_id varchar(80),
    @fencing_token bigint,
    @attempt_number int,
    @event_code varchar(48),
    @event_bytes varbinary(max),
    @event_fingerprint binary(32)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF HASHBYTES('SHA2_256', @event_bytes) <> @event_fingerprint
        THROW 51226, 'ASKLEGAL_ATTEMPT_BYTES_FINGERPRINT_MISMATCH', 1;
    IF NOT EXISTS
    (
        SELECT 1 FROM register.effect_claim_current
        WHERE effect_intent_id = @effect_intent_id
          AND claimant_id = @claimant_id
          AND fencing_token = @fencing_token
          AND expires_at > SYSUTCDATETIME()
    ) THROW 51227, 'ASKLEGAL_STALE_FENCING_TOKEN', 1;
    IF @attempt_number < 1 OR @attempt_number >
       (SELECT attempt_ceiling FROM register.effect_intent_fact
        WHERE effect_intent_id = @effect_intent_id)
        THROW 51228, 'ASKLEGAL_EFFECT_ATTEMPT_INVALID', 1;

    INSERT register.effect_attempt_fact
        (effect_intent_id, attempt_number, fencing_token, event_code,
         event_bytes, event_fingerprint, recorded_at)
    VALUES
        (@effect_intent_id, @attempt_number, @fencing_token, @event_code,
         @event_bytes, @event_fingerprint, SYSUTCDATETIME());
END;
