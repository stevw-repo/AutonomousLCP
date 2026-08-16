CREATE PROCEDURE register.renew_effect_claim_v1
    @effect_intent_id varchar(80),
    @claimant_id varchar(80),
    @fencing_token bigint,
    @lease_seconds int
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @lease_seconds < 1 THROW 51220, 'ASKLEGAL_EFFECT_LEASE_INVALID', 1;
    UPDATE register.effect_claim_current
    SET claimed_at = SYSUTCDATETIME(),
        expires_at = DATEADD(second, @lease_seconds, SYSUTCDATETIME())
    WHERE effect_intent_id = @effect_intent_id
      AND claimant_id = @claimant_id
      AND fencing_token = @fencing_token
      AND expires_at > SYSUTCDATETIME();
    IF @@ROWCOUNT <> 1 THROW 51227, 'ASKLEGAL_STALE_FENCING_TOKEN', 1;
    SELECT effect_intent_id, claimant_id, generation, fencing_token,
           claimed_at, expires_at
    FROM register.effect_claim_current WHERE effect_intent_id = @effect_intent_id;
END;
