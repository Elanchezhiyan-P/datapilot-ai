/*
    04 - Check that DataPilotLab is set up correctly. Changes nothing.

    Run with an ADMIN login, after 03_create_readonly_login.sql. It checks the row
    counts, then acts as datapilot_reader (EXECUTE AS) to prove the login can read,
    can see CHECK constraint text, and cannot write. Every line should say PASS.
*/
USE DataPilotLab;
GO

SET NOCOUNT ON;

DECLARE @checks TABLE (Result CHAR(4), [Check] NVARCHAR(200), Detail NVARCHAR(400));

-- 1. Row counts produced by 02_seed_data.sql
DECLARE @expected TABLE (TableName SYSNAME, ExpectedRows INT);
INSERT @expected VALUES (N'Schools', 40), (N'Students', 3000), (N'Exams', 18),
                        (N'Registrations', 5443), (N'Payments', 5443), (N'Results', 4886);

INSERT @checks
SELECT CASE WHEN ISNULL(p.RowsFound, -1) = e.ExpectedRows THEN 'PASS' ELSE 'FAIL' END,
       CONCAT(N'Row count of dbo.', e.TableName),
       CONCAT(N'expected ', e.ExpectedRows, N', found ', ISNULL(CAST(p.RowsFound AS NVARCHAR(20)), N'no table'))
FROM @expected e
LEFT JOIN (
    SELECT t.name, SUM(ps.row_count) AS RowsFound
    FROM sys.tables t
    JOIN sys.dm_db_partition_stats ps ON ps.object_id = t.object_id AND ps.index_id IN (0, 1)
    GROUP BY t.name
) p ON p.name = e.TableName;

-- 2. A spot check of the data itself: the README's example answer.
INSERT @checks
SELECT CASE WHEN COUNT(*) = 409 THEN 'PASS' ELSE 'FAIL' END,
       N'Students at schools in Coimbatore',
       CONCAT(N'expected 409, found ', COUNT(*))
FROM dbo.Students s JOIN dbo.Schools sc ON sc.SchoolId = s.SchoolId
WHERE sc.City = N'Coimbatore';

-- 3. The read-only login, tested by impersonating it.
IF DATABASE_PRINCIPAL_ID(N'datapilot_reader') IS NULL
BEGIN
    INSERT @checks VALUES ('FAIL', N'datapilot_reader user exists', N'run 03_create_readonly_login.sql');
END
ELSE
BEGIN
    INSERT @checks VALUES ('PASS', N'datapilot_reader user exists', N'');

    EXECUTE AS USER = N'datapilot_reader';

    DECLARE @canRead INT = (SELECT COUNT(*) FROM dbo.Schools);
    DECLARE @canSeeChecks BIT = CASE WHEN EXISTS (
        SELECT 1 FROM sys.check_constraints WHERE definition IS NOT NULL) THEN 1 ELSE 0 END;
    DECLARE @insertError NVARCHAR(400) = NULL;

    BEGIN TRY
        BEGIN TRANSACTION;   -- rolled back below even if the INSERT were allowed
        INSERT dbo.Schools (SchoolName, City, State, SchoolType)
        VALUES (N'Permission test', N'Test', N'Test', N'Private');
        ROLLBACK TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        SET @insertError = ERROR_MESSAGE();
    END CATCH;

    REVERT;

    INSERT @checks VALUES
        (CASE WHEN @canRead = 40 THEN 'PASS' ELSE 'FAIL' END,
         N'datapilot_reader can read tables', CONCAT(N'read ', @canRead, N' schools')),
        (CASE WHEN @canSeeChecks = 1 THEN 'PASS' ELSE 'FAIL' END,
         N'datapilot_reader can see CHECK constraint text (VIEW DEFINITION)',
         CASE WHEN @canSeeChecks = 1 THEN N'' ELSE N'run GRANT VIEW DEFINITION TO datapilot_reader' END),
        (CASE WHEN @insertError LIKE N'%permission was denied%' THEN 'PASS' ELSE 'FAIL' END,
         N'datapilot_reader cannot write',
         ISNULL(@insertError, N'INSERT was allowed: the login is NOT read-only'));
END;

SELECT Result, [Check], Detail FROM @checks;

IF EXISTS (SELECT 1 FROM @checks WHERE Result = 'FAIL')
    RAISERROR ('Some checks failed. See the rows marked FAIL above.', 16, 1);
ELSE
    PRINT 'All checks passed.';
GO
