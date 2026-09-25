/*
    03 - Read-only SQL login for DataPilot.

    Run in SSMS with an ADMIN login, after 02_seed_data.sql. Safe to re-run.
    Before running: replace <choose-a-strong-password> below, and put the same value
    in .env as DB_PASSWORD. (If the login already exists, its password is not changed.)
    Requires SQL Server authentication (mixed mode) to be enabled; see sql/README.md.

    Next: 04_verify_setup.sql
*/
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'datapilot_reader')
    CREATE LOGIN datapilot_reader WITH PASSWORD = N'<choose-a-strong-password>';
GO

USE DataPilotLab;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'datapilot_reader')
    CREATE USER datapilot_reader FOR LOGIN datapilot_reader;
GO

-- Read every table, nothing else. Writes are refused by the database itself.
ALTER ROLE db_datareader ADD MEMBER datapilot_reader;

-- Lets schema discovery read CHECK constraint text (the allowed values of Status,
-- Award, ...). Metadata only: it grants no extra data access and no writes.
GRANT VIEW DEFINITION TO datapilot_reader;
GO
