/*
    00 - Create the DataPilotLab database.

    Run in SSMS (or sqlcmd) with an ADMIN login. Safe to re-run: does nothing if the
    database already exists. Files go to the server's default data and log folders.

    Next: 01_create_tables.sql
*/
USE master;
GO

IF DB_ID(N'DataPilotLab') IS NULL
BEGIN
    CREATE DATABASE DataPilotLab;
    PRINT 'Created database DataPilotLab.';
END
ELSE
    PRINT 'Database DataPilotLab already exists; nothing to do.';
GO

-- A lab database: no point-in-time restore needed, so keep the log small.
ALTER DATABASE DataPilotLab SET RECOVERY SIMPLE;
GO
