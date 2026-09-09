CREATE OR ALTER PROCEDURE promotion.activate_serving_state_v1
    @expected_base_state_id varchar(80), @state_id varchar(80), @state_fingerprint varchar(71),
    @predecessor_state_id varchar(80), @target_name varchar(80),
    @desired_inventory_fingerprint varchar(71), @coverage_fingerprint varchar(71),
    @embedding_profile_id varchar(80), @embedding_profile_fingerprint varchar(71),
    @approval_id varchar(80), @execution_lineage_id varchar(80)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON; SET LOCK_TIMEOUT 5000;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    DECLARE @current varchar(80); DECLARE @receipt_id varchar(80);
    IF USER_NAME() NOT IN ('asklegal_promotion_app', 'dbo')
        THROW 52101, 'ASKLEGAL_SERVING_STATE_OWNER_MISMATCH', 1;
    IF @expected_base_state_id IS NULL OR @state_id IS NULL OR @state_fingerprint IS NULL OR
       @predecessor_state_id <> @expected_base_state_id OR @target_name IS NULL OR
       @desired_inventory_fingerprint IS NULL OR @coverage_fingerprint IS NULL OR
       @embedding_profile_id IS NULL OR @embedding_profile_fingerprint IS NULL OR
       @approval_id IS NULL OR @execution_lineage_id IS NULL
        THROW 52102, 'ASKLEGAL_SERVING_STATE_INPUT_INVALID', 1;
    BEGIN TRANSACTION;
    BEGIN TRY
        SELECT @current = state_id FROM promotion.serving_state_v1_current WITH (UPDLOCK, HOLDLOCK)
        WHERE singleton_id = 1;
        SELECT @receipt_id = receipt_id FROM promotion.serving_state_v1_fact WITH (UPDLOCK, HOLDLOCK)
        WHERE operation_code = 'ACTIVATED' AND predecessor_state_id = @expected_base_state_id
          AND state_id = @state_id AND state_fingerprint = @state_fingerprint
          AND target_name = @target_name AND desired_inventory_fingerprint = @desired_inventory_fingerprint
          AND coverage_fingerprint = @coverage_fingerprint AND embedding_profile_id = @embedding_profile_id
          AND embedding_profile_fingerprint = @embedding_profile_fingerprint
          AND approval_id = @approval_id AND execution_lineage_id = @execution_lineage_id;
        IF @receipt_id IS NOT NULL
        BEGIN
            IF @current <> @state_id OR NOT EXISTS
                (SELECT 1 FROM promotion.serving_state_v1_current WHERE singleton_id = 1
                 AND last_receipt_id = @receipt_id)
                THROW 52103, 'ASKLEGAL_SERVING_STATE_BASE_STATE_DRIFT', 1;
            SELECT receipt_id, operation_code, predecessor_state_id, state_id, state_fingerprint,
                   CAST(1 AS bit) AS replayed FROM promotion.serving_state_v1_fact WHERE receipt_id = @receipt_id;
            COMMIT TRANSACTION; RETURN;
        END;
        IF @current IS NULL OR @current <> @expected_base_state_id
            THROW 52103, 'ASKLEGAL_SERVING_STATE_BASE_STATE_DRIFT', 1;
        SET @receipt_id = CONCAT('ssr_', LOWER(CONVERT(varchar(64), HASHBYTES('SHA2_256',
            CONCAT(@expected_base_state_id, '|', @state_id, '|', @state_fingerprint, '|', @target_name,
            '|', @desired_inventory_fingerprint, '|', @coverage_fingerprint, '|', @embedding_profile_id,
            '|', @embedding_profile_fingerprint, '|', @approval_id, '|', @execution_lineage_id)), 2)));
        INSERT promotion.serving_state_v1_fact
            (receipt_id, operation_code, predecessor_state_id, state_id, state_fingerprint, target_name,
             desired_inventory_fingerprint, coverage_fingerprint, embedding_profile_id,
             embedding_profile_fingerprint, approval_id, execution_lineage_id, recorded_at)
        VALUES (@receipt_id, 'ACTIVATED', @expected_base_state_id, @state_id, @state_fingerprint,
             @target_name, @desired_inventory_fingerprint, @coverage_fingerprint, @embedding_profile_id,
             @embedding_profile_fingerprint, @approval_id, @execution_lineage_id, SYSUTCDATETIME());
        UPDATE promotion.serving_state_v1_current SET state_id = @state_id, last_receipt_id = @receipt_id,
            updated_at = SYSUTCDATETIME() WHERE singleton_id = 1;
        SELECT @receipt_id, 'ACTIVATED', @expected_base_state_id, @state_id, @state_fingerprint,
               CAST(0 AS bit); COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        IF ERROR_NUMBER() = 1222 THROW 52104, 'ASKLEGAL_SERVING_STATE_LOCK_TIMEOUT', 1;
        THROW;
    END CATCH;
END;
