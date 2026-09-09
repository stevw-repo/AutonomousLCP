CREATE OR ALTER PROCEDURE promotion.read_serving_state_v1
AS
BEGIN
    SET NOCOUNT ON;
    SET LOCK_TIMEOUT 5000;
    DECLARE @caller varchar(48) = CASE USER_NAME()
        WHEN 'asklegal_promotion_app' THEN 'PROMOTION_WORKER' WHEN 'dbo' THEN 'DBO' ELSE NULL END;
    IF @caller IS NULL THROW 52100, 'ASKLEGAL_SERVING_STATE_OWNER_MISMATCH', 1;
    BEGIN TRY
        SELECT state_id FROM promotion.serving_state_v1_current WITH (READCOMMITTEDLOCK)
        WHERE singleton_id = 1;
    END TRY
    BEGIN CATCH
        IF ERROR_NUMBER() = 1222 THROW 52100, 'ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT', 1;
        THROW;
    END CATCH;
END;
