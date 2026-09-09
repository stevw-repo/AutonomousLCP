CREATE OR ALTER PROCEDURE promotion.rollback_serving_state_v1
    @candidate_state_id varchar(80), @predecessor_state_id varchar(80),
    @activation_receipt_id varchar(80)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON; SET LOCK_TIMEOUT 5000;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    DECLARE @current varchar(80); DECLARE @activation_receipt varchar(80);
    DECLARE @rollback_receipt varchar(80); DECLARE @fingerprint varchar(71);
    IF USER_NAME() NOT IN ('asklegal_promotion_app', 'dbo')
        THROW 52105, 'ASKLEGAL_SERVING_STATE_OWNER_MISMATCH', 1;
    IF @candidate_state_id IS NULL OR @predecessor_state_id IS NULL OR @activation_receipt_id IS NULL
        THROW 52106, 'ASKLEGAL_SERVING_STATE_INPUT_INVALID', 1;
    BEGIN TRANSACTION;
    BEGIN TRY
        SELECT @current = state_id, @activation_receipt = last_receipt_id
        FROM promotion.serving_state_v1_current WITH (UPDLOCK, HOLDLOCK) WHERE singleton_id = 1;
        SET @rollback_receipt = CONCAT('ssr_', LOWER(CONVERT(varchar(64), HASHBYTES('SHA2_256',
            CONCAT('rollback|', @activation_receipt_id, '|', @candidate_state_id, '|', @predecessor_state_id)), 2)));
        IF @current = @predecessor_state_id AND EXISTS
            (SELECT 1 FROM promotion.serving_state_v1_current WHERE singleton_id = 1
             AND last_receipt_id = @rollback_receipt)
        BEGIN
            SELECT receipt_id, operation_code, predecessor_state_id, state_id, state_fingerprint,
                   CAST(1 AS bit) AS replayed FROM promotion.serving_state_v1_fact
            WHERE receipt_id = @rollback_receipt AND operation_code = 'ROLLED_BACK'
              AND predecessor_state_id = @candidate_state_id AND state_id = @predecessor_state_id;
            COMMIT TRANSACTION; RETURN;
        END;
        IF @current <> @candidate_state_id OR @activation_receipt <> @activation_receipt_id
            THROW 52108, 'ASKLEGAL_SERVING_STATE_ROLLBACK_DRIFT', 1;
        SELECT @fingerprint = state_fingerprint FROM promotion.serving_state_v1_fact WITH (UPDLOCK, HOLDLOCK)
        WHERE receipt_id = @activation_receipt_id AND operation_code = 'ACTIVATED'
          AND state_id = @candidate_state_id AND predecessor_state_id = @predecessor_state_id;
        IF @fingerprint IS NULL THROW 52107, 'ASKLEGAL_SERVING_STATE_ROLLBACK_BINDING_INVALID', 1;
        IF EXISTS (SELECT 1 FROM promotion.serving_state_v1_fact WITH (UPDLOCK, HOLDLOCK)
                   WHERE receipt_id = @rollback_receipt)
            THROW 52108, 'ASKLEGAL_SERVING_STATE_ROLLBACK_DRIFT', 1;
        INSERT promotion.serving_state_v1_fact
            (receipt_id, operation_code, predecessor_state_id, state_id, state_fingerprint, target_name,
             desired_inventory_fingerprint, coverage_fingerprint, embedding_profile_id,
             embedding_profile_fingerprint, approval_id, execution_lineage_id, recorded_at)
        SELECT @rollback_receipt, 'ROLLED_BACK', @candidate_state_id, @predecessor_state_id,
               state_fingerprint, target_name, desired_inventory_fingerprint, coverage_fingerprint,
               embedding_profile_id, embedding_profile_fingerprint, approval_id, execution_lineage_id,
               SYSUTCDATETIME() FROM promotion.serving_state_v1_fact WHERE receipt_id = @activation_receipt_id;
        UPDATE promotion.serving_state_v1_current SET state_id = @predecessor_state_id,
            last_receipt_id = @rollback_receipt, updated_at = SYSUTCDATETIME() WHERE singleton_id = 1;
        SELECT @rollback_receipt, 'ROLLED_BACK', @candidate_state_id, @predecessor_state_id,
               @fingerprint, CAST(0 AS bit); COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        IF ERROR_NUMBER() = 1222 THROW 52109, 'ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT', 1;
        THROW;
    END CATCH;
END;
