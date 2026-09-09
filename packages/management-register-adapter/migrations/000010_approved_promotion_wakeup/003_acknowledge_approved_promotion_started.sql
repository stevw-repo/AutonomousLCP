CREATE PROCEDURE promotion.acknowledge_approved_promotion_started_v1
    @approval_id varchar(80),
    @proposal_package_id varchar(80),
    @decision_fingerprint binary(32),
    @manifest_id varchar(80),
    @manifest_fingerprint varchar(71),
    @worker_id varchar(80),
    @claimed_until datetime2(7),
    @generation bigint,
    @fencing_token bigint,
    @execution_lineage_id varchar(80)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET LOCK_TIMEOUT 5000;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

    DECLARE @now datetime2(7) = SYSUTCDATETIME();
    DECLARE @caller_application varchar(48) =
        CASE USER_NAME()
            WHEN 'asklegal_promotion_app' THEN 'PROMOTION_WORKER'
            WHEN 'dbo' THEN 'DBO'
            ELSE NULL
        END;

    IF @caller_application IS NULL
        THROW 52010, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_OWNER_MISMATCH', 1;
    IF @approval_id IS NULL OR @proposal_package_id IS NULL OR @decision_fingerprint IS NULL OR
       @manifest_id IS NULL OR @manifest_fingerprint IS NULL OR @worker_id IS NULL OR
       @claimed_until IS NULL OR @generation < 1 OR @fencing_token < 1 OR
       @execution_lineage_id IS NULL
        THROW 52011, 'ASKLEGAL_APPROVED_PROMOTION_ACKNOWLEDGEMENT_INVALID', 1;

    BEGIN TRANSACTION;
    BEGIN TRY
        IF EXISTS
        (
            SELECT 1
            FROM promotion.approved_promotion_acknowledgement_fact WITH (UPDLOCK, HOLDLOCK)
            WHERE approval_id = @approval_id
              AND proposal_package_id = @proposal_package_id
              AND decision_fingerprint = @decision_fingerprint
              AND manifest_id = @manifest_id
              AND manifest_fingerprint = @manifest_fingerprint
              AND claimant_worker_id = @worker_id
              AND claimed_until = @claimed_until
              AND generation = @generation
              AND fencing_token = @fencing_token
              AND execution_lineage_id = @execution_lineage_id
        )
        BEGIN
            SELECT approval_id, execution_lineage_id, fencing_token
            FROM promotion.approved_promotion_acknowledgement_fact
            WHERE approval_id = @approval_id;
            COMMIT TRANSACTION;
            RETURN;
        END;
        IF EXISTS
        (
            SELECT 1
            FROM promotion.approved_promotion_acknowledgement_fact WITH (UPDLOCK, HOLDLOCK)
            WHERE approval_id = @approval_id
        )
            THROW 52012, 'ASKLEGAL_APPROVED_PROMOTION_ACKNOWLEDGEMENT_REPLAY_MISMATCH', 1;
        IF NOT EXISTS
        (
            SELECT 1
            FROM promotion.approved_promotion_claim_current WITH (UPDLOCK, HOLDLOCK)
            WHERE approval_id = @approval_id
              AND proposal_package_id = @proposal_package_id
              AND decision_fingerprint = @decision_fingerprint
              AND manifest_id = @manifest_id
              AND manifest_fingerprint = @manifest_fingerprint
              AND claimant_worker_id = @worker_id
              AND claimed_until = @claimed_until
              AND generation = @generation
              AND fencing_token = @fencing_token
              AND claimed_until > @now
        )
            THROW 52013, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_STALE_CLAIM', 1;
        IF EXISTS
        (
            SELECT 1
            FROM register.event_v1_fact terminal WITH (UPDLOCK, HOLDLOCK)
            WHERE
                (terminal.owning_application = 'REVIEW_APPLICATION'
                 AND terminal.aggregate_id = @proposal_package_id
                 AND terminal.event_type IN ('APPROVAL_REVOKED', 'APPROVAL_INVALIDATED')
                 AND JSON_VALUE(
                       CONVERT(varchar(max), terminal.event_bytes), '$.approval_ref.ref_id'
                     ) = @approval_id)
                OR
                (terminal.owning_application = 'PROMOTION_WORKER'
                 AND terminal.aggregate_id = @approval_id
                 AND terminal.event_type = 'APPROVAL_INVALIDATED')
        )
            THROW 52014, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_APPROVAL_TERMINAL', 1;
        IF NOT EXISTS
        (
            SELECT 1
            FROM register.event_v1_fact consumed WITH (UPDLOCK, HOLDLOCK)
            INNER JOIN register.command_v1_fact command WITH (HOLDLOCK)
              ON command.owning_application = consumed.owning_application
             AND command.command_id = consumed.command_id
            WHERE consumed.owning_application = 'PROMOTION_WORKER'
              AND consumed.aggregate_id = @approval_id
              AND consumed.event_type = 'APPROVAL_CONSUMED'
              AND JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes), '$.approval_ref.ref_id'
                  ) = @approval_id
              AND JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes), '$.approval_ref.fingerprint'
                  ) = CONCAT('sha256:', LOWER(CONVERT(varchar(64), @decision_fingerprint, 2)))
              AND JSON_VALUE(
                    CONVERT(varchar(max), consumed.event_bytes),
                    '$.execution_lineage_refs[0].ref_id'
                  ) = @execution_lineage_id
              AND JSON_VALUE(CONVERT(varchar(max), command.command_bytes), '$.action') =
                  'CONSUME_REGISTERED_APPROVAL'
              AND JSON_VALUE(CONVERT(varchar(max), command.command_bytes), '$.approval_id') =
                  @approval_id
              AND JSON_VALUE(CONVERT(varchar(max), command.command_bytes), '$.proposal_package_id') =
                  @proposal_package_id
              AND JSON_VALUE(CONVERT(varchar(max), command.command_bytes),
                    '$.decision_fingerprint') =
                  CONCAT('sha256:', LOWER(CONVERT(varchar(64), @decision_fingerprint, 2)))
              AND JSON_VALUE(CONVERT(varchar(max), command.command_bytes), '$.manifest_id') =
                  @manifest_id
              AND JSON_VALUE(CONVERT(varchar(max), command.command_bytes),
                    '$.manifest_fingerprint') = @manifest_fingerprint
              AND JSON_VALUE(CONVERT(varchar(max), command.command_bytes),
                    '$.execution_lineage_id') = @execution_lineage_id
        )
            THROW 52015, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_NOT_CONSUMED', 1;

        INSERT promotion.approved_promotion_acknowledgement_fact
            (approval_id, proposal_package_id, decision_fingerprint, manifest_id,
             manifest_fingerprint, claimant_worker_id, claimed_until, generation,
             fencing_token, execution_lineage_id, acknowledged_at)
        VALUES
            (@approval_id, @proposal_package_id, @decision_fingerprint, @manifest_id,
             @manifest_fingerprint, @worker_id, @claimed_until, @generation,
             @fencing_token, @execution_lineage_id, @now);

        SELECT @approval_id, @execution_lineage_id, @fencing_token;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        IF ERROR_NUMBER() = 1222
            THROW 52017, 'ASKLEGAL_APPROVED_PROMOTION_ACKNOWLEDGEMENT_LOCK_TIMEOUT', 1;
        THROW;
    END CATCH;
END;
