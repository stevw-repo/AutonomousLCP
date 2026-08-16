CREATE PROCEDURE register.rebuild_projection_v1
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRANSACTION;
    DELETE FROM register.projection_checkpoint_current;
    DECLARE @checkpoint bigint = (SELECT COUNT(*) FROM register.event_v1_fact);
    DECLARE @source_event_id varchar(80);
    DECLARE @source_event_fingerprint binary(32);
    SELECT TOP (1)
        @source_event_id = event_id,
        @source_event_fingerprint = event_fingerprint
    FROM register.event_v1_fact
    ORDER BY recorded_at DESC, event_id DESC;
    INSERT register.projection_checkpoint_current
        (projection_name, source_event_id, source_event_fingerprint,
         checkpoint_sequence, rebuilt_at)
    VALUES
        ('aggregate_status_v1', @source_event_id, @source_event_fingerprint,
         @checkpoint, SYSUTCDATETIME());
    COMMIT TRANSACTION;
END;
