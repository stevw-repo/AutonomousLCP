CREATE PROCEDURE promotion.claim_next_approved_promotion_v1
    @worker_id varchar(80),
    @claimed_until datetime2(7)
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
    DECLARE @proposal_package_id varchar(80);
    DECLARE @approval_id varchar(80);
    DECLARE @decision_fingerprint binary(32);
    DECLARE @manifest_id varchar(80);
    DECLARE @manifest_fingerprint varchar(71);
    DECLARE @generation bigint;
    DECLARE @fencing_token bigint;

    IF @caller_application IS NULL
        THROW 52000, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_OWNER_MISMATCH', 1;
    IF @worker_id IS NULL OR LEN(@worker_id) <> 52 OR LEFT(@worker_id, 4) <> 'pwr_' OR
       RIGHT(@worker_id, 48) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%'
        THROW 52001, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_WORKER_INVALID', 1;
    IF @claimed_until IS NULL OR @claimed_until <= @now
        THROW 52002, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_LEASE_INVALID', 1;

    BEGIN TRANSACTION;
    BEGIN TRY
        SELECT TOP (1)
            @proposal_package_id = p.proposal_package_id,
            @approval_id = JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.approval_id'),
            @decision_fingerprint = p.decision_fingerprint,
            @manifest_id = JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes), '$.promotion_manifest_ref.ref_id'
            ),
            @manifest_fingerprint = JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.promotion_manifest_ref.fingerprint'
            )
        FROM review.proposal_package_review_v1 p WITH (UPDLOCK, HOLDLOCK)
        LEFT JOIN promotion.approved_promotion_acknowledgement_fact acknowledged
          WITH (UPDLOCK, HOLDLOCK)
          ON acknowledged.approval_id = JSON_VALUE(
              CONVERT(varchar(max), p.decision_bytes), '$.approval_id'
          )
        WHERE p.review_version = 1
          AND p.decision_event_type = 'PROPOSAL_APPROVED'
          AND p.decision_bytes IS NOT NULL
          AND p.decision_fingerprint IS NOT NULL
          AND ISJSON(CONVERT(varchar(max), p.decision_bytes)) = 1
          AND (SELECT COUNT(*) FROM OPENJSON(CONVERT(varchar(max), p.decision_bytes))) = 14
          AND JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.schema_id') =
              'asklegal.approval-decision'
          AND JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.schema_version') = '1.1.0'
          AND JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.decision') = 'APPROVED'
          AND JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.governance_policy_state') =
              'CONFIGURED'
          AND JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.immutable') = 'true'
          AND JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.approval_id') LIKE 'apr[_]%'
          AND LEN(JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.approval_id')) = 52
          AND RIGHT(JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.approval_id'), 48)
              COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
          AND JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes), '$.promotion_manifest_ref.ref_type'
              ) = 'PROMOTION_MANIFEST'
          AND JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes), '$.promotion_manifest_ref.ref_id'
              ) LIKE 'pmn[_]%'
          AND LEN(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes), '$.promotion_manifest_ref.ref_id'
              )) = 52
          AND RIGHT(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes), '$.promotion_manifest_ref.ref_id'
              ), 48) COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
          AND LEN(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.promotion_manifest_ref.fingerprint'
              )) = 71
          AND LEFT(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.promotion_manifest_ref.fingerprint'
              ), 7) = 'sha256:'
          AND RIGHT(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.promotion_manifest_ref.fingerprint'
              ), 64) COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
          AND JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.expected_base_serving_state_ref.ref_type'
              ) = 'SERVING_STATE'
          AND JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.expected_base_serving_state_ref.ref_id'
              ) LIKE 'srv[_]%'
          AND LEN(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.expected_base_serving_state_ref.ref_id'
              )) = 52
          AND RIGHT(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes), '$.expected_base_serving_state_ref.ref_id'
              ), 48) COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
          AND LEN(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.expected_base_serving_state_ref.fingerprint'
              )) = 71
          AND LEFT(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.expected_base_serving_state_ref.fingerprint'
              ), 7) = 'sha256:'
          AND RIGHT(JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes),
                '$.expected_base_serving_state_ref.fingerprint'
              ), 64) COLLATE Latin1_General_100_BIN2 NOT LIKE '%[^0-9a-f]%'
          AND TRY_CONVERT(datetimeoffset(7), JSON_VALUE(
                CONVERT(varchar(max), p.decision_bytes), '$.valid_from'
              ), 127) <= TODATETIMEOFFSET(@now, '+00:00')
          AND acknowledged.approval_id IS NULL
          AND NOT EXISTS
          (
              SELECT 1
              FROM register.event_v1_fact terminal WITH (UPDLOCK, HOLDLOCK)
              WHERE
                  (terminal.owning_application = 'REVIEW_APPLICATION'
                   AND terminal.aggregate_id = p.proposal_package_id
                   AND terminal.event_type IN ('APPROVAL_REVOKED', 'APPROVAL_INVALIDATED')
                   AND JSON_VALUE(
                         CONVERT(varchar(max), terminal.event_bytes), '$.approval_ref.ref_id'
                       ) = JSON_VALUE(CONVERT(varchar(max), p.decision_bytes), '$.approval_id'))
                  OR
                  (terminal.owning_application = 'PROMOTION_WORKER'
                   AND terminal.aggregate_id = JSON_VALUE(
                         CONVERT(varchar(max), p.decision_bytes), '$.approval_id'
                       )
                   AND terminal.event_type IN ('APPROVAL_CONSUMED', 'APPROVAL_INVALIDATED'))
          )
          AND NOT EXISTS
          (
              SELECT 1
              FROM promotion.approved_promotion_claim_current current_claim
                  WITH (UPDLOCK, HOLDLOCK)
              WHERE current_claim.approval_id = JSON_VALUE(
                        CONVERT(varchar(max), p.decision_bytes), '$.approval_id'
                    )
                AND current_claim.claimed_until > @now
                AND current_claim.claimant_worker_id <> @worker_id
          )
        ORDER BY p.decision_at, p.proposal_package_id;

        IF @approval_id IS NULL
        BEGIN
            COMMIT TRANSACTION;
            RETURN;
        END;

        IF EXISTS
        (
            SELECT 1
            FROM promotion.approved_promotion_claim_current WITH (UPDLOCK, HOLDLOCK)
            WHERE approval_id = @approval_id
              AND claimed_until > @now
              AND claimant_worker_id = @worker_id
              AND claimed_until <> @claimed_until
        )
            THROW 52003, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_REPLAY_MISMATCH', 1;

        IF EXISTS
        (
            SELECT 1
            FROM promotion.approved_promotion_claim_current WITH (UPDLOCK, HOLDLOCK)
            WHERE approval_id = @approval_id
              AND claimed_until > @now
              AND claimant_worker_id = @worker_id
              AND claimed_until = @claimed_until
        )
        BEGIN
            SELECT @generation = generation, @fencing_token = fencing_token
            FROM promotion.approved_promotion_claim_current
            WHERE approval_id = @approval_id;
        END
        ELSE IF EXISTS
        (
            SELECT 1
            FROM promotion.approved_promotion_claim_current WITH (UPDLOCK, HOLDLOCK)
            WHERE approval_id = @approval_id
        )
        BEGIN
            UPDATE promotion.approved_promotion_claim_current
            SET proposal_package_id = @proposal_package_id,
                decision_fingerprint = @decision_fingerprint,
                manifest_id = @manifest_id,
                manifest_fingerprint = @manifest_fingerprint,
                claimant_worker_id = @worker_id,
                claimed_at = @now,
                claimed_until = @claimed_until,
                generation = generation + 1,
                fencing_token = fencing_token + 1
            WHERE approval_id = @approval_id;
            SELECT @generation = generation, @fencing_token = fencing_token
            FROM promotion.approved_promotion_claim_current
            WHERE approval_id = @approval_id;
        END
        ELSE
        BEGIN
            INSERT promotion.approved_promotion_claim_current
                (approval_id, proposal_package_id, decision_fingerprint, manifest_id,
                 manifest_fingerprint, claimant_worker_id, claimed_at, claimed_until,
                 generation, fencing_token)
            VALUES
                (@approval_id, @proposal_package_id, @decision_fingerprint, @manifest_id,
                 @manifest_fingerprint, @worker_id, @now, @claimed_until, 1, 1);
            SET @generation = 1;
            SET @fencing_token = 1;
        END;

        SELECT proposal_package_id, approval_id, decision_fingerprint, manifest_id,
               manifest_fingerprint, claimant_worker_id,
               CONCAT(CONVERT(varchar(33), claimed_until, 127), 'Z') AS claimed_until,
               generation, fencing_token
        FROM promotion.approved_promotion_claim_current
        WHERE approval_id = @approval_id
          AND generation = @generation
          AND fencing_token = @fencing_token;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        IF ERROR_NUMBER() = 1222
            THROW 52016, 'ASKLEGAL_APPROVED_PROMOTION_QUEUE_LOCK_TIMEOUT', 1;
        THROW;
    END CATCH;
END;
