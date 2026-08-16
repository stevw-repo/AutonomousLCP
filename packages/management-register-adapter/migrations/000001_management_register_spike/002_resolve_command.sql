CREATE PROCEDURE register.resolve_command
    @command_id varchar(80),
    @command_fingerprint binary(32)
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS
    (
        SELECT 1
        FROM register.command_fact
        WHERE command_id = @command_id
          AND command_fingerprint <> @command_fingerprint
    )
        THROW 51001, 'ASKLEGAL_COMMAND_FINGERPRINT_MISMATCH', 1;

    SELECT command_id, result_code, result_bytes, CAST(1 AS bit) AS replayed
    FROM register.command_fact
    WHERE command_id = @command_id
      AND command_fingerprint = @command_fingerprint;
END;
