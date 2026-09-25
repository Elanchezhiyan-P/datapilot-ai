/*
    01 - Create the DataPilotLab tables.

    Run in SSMS (or sqlcmd) with an ADMIN login, after 00_create_database.sql.
    WARNING: drops and recreates all six tables, deleting their data.
    Then run 02_seed_data.sql to fill them.
*/
USE DataPilotLab;
GO

SET NOCOUNT ON;

DROP TABLE IF EXISTS dbo.Results, dbo.Payments, dbo.Registrations, dbo.Exams, dbo.Students, dbo.Schools;
GO


------------------------------------------------------------------------------
-- Schema
------------------------------------------------------------------------------
CREATE TABLE dbo.Schools (
    SchoolId    INT IDENTITY(1,1) CONSTRAINT PK_Schools PRIMARY KEY,
    SchoolName  NVARCHAR(150) NOT NULL,
    City        NVARCHAR(50)  NOT NULL,
    State       NVARCHAR(50)  NOT NULL,
    SchoolType  NVARCHAR(20)  NOT NULL
        CONSTRAINT CK_Schools_SchoolType CHECK (SchoolType IN (N'Private', N'Government', N'Aided')),
    CreatedAt   DATETIME2(0)  NOT NULL CONSTRAINT DF_Schools_CreatedAt DEFAULT SYSUTCDATETIME()
);

CREATE TABLE dbo.Students (
    StudentId     INT IDENTITY(1,1) CONSTRAINT PK_Students PRIMARY KEY,
    SchoolId      INT NOT NULL CONSTRAINT FK_Students_Schools REFERENCES dbo.Schools (SchoolId),
    FirstName     NVARCHAR(50) NOT NULL,
    LastName      NVARCHAR(50) NOT NULL,
    Gender        CHAR(1)      NOT NULL CONSTRAINT CK_Students_Gender CHECK (Gender IN ('M', 'F')),
    DateOfBirth   DATE         NOT NULL,
    CurrentGrade  TINYINT      NOT NULL CONSTRAINT CK_Students_CurrentGrade CHECK (CurrentGrade BETWEEN 1 AND 12),
    CreatedAt     DATETIME2(0) NOT NULL
);

CREATE TABLE dbo.Exams (
    ExamId     INT IDENTITY(1,1) CONSTRAINT PK_Exams PRIMARY KEY,
    ExamYear   SMALLINT     NOT NULL,
    LevelName  NVARCHAR(20) NOT NULL,
    MinGrade   TINYINT      NOT NULL,
    MaxGrade   TINYINT      NOT NULL,
    ExamDate   DATE         NOT NULL,
    MaxScore   SMALLINT     NOT NULL,
    CONSTRAINT UQ_Exams_ExamYear_LevelName UNIQUE (ExamYear, LevelName)
);

CREATE TABLE dbo.Registrations (
    RegistrationId  INT IDENTITY(1,1) CONSTRAINT PK_Registrations PRIMARY KEY,
    StudentId       INT NOT NULL CONSTRAINT FK_Registrations_Students REFERENCES dbo.Students (StudentId),
    ExamId          INT NOT NULL CONSTRAINT FK_Registrations_Exams REFERENCES dbo.Exams (ExamId),
    RegisteredAt    DATETIME2(0) NOT NULL,
    Status          NVARCHAR(20) NOT NULL
        CONSTRAINT CK_Registrations_Status CHECK (Status IN (N'Completed', N'Absent', N'Cancelled')),
    CONSTRAINT UQ_Registrations_StudentId_ExamId UNIQUE (StudentId, ExamId)
);

CREATE TABLE dbo.Payments (
    PaymentId       INT IDENTITY(1,1) CONSTRAINT PK_Payments PRIMARY KEY,
    RegistrationId  INT NOT NULL CONSTRAINT FK_Payments_Registrations REFERENCES dbo.Registrations (RegistrationId),
    Amount          DECIMAL(10,2) NOT NULL,
    Currency        CHAR(3)       NOT NULL CONSTRAINT DF_Payments_Currency DEFAULT 'INR',
    PaymentMethod   NVARCHAR(20)  NOT NULL
        CONSTRAINT CK_Payments_PaymentMethod CHECK (PaymentMethod IN (N'UPI', N'Card', N'NetBanking', N'Cash')),
    PaymentStatus   NVARCHAR(20)  NOT NULL
        CONSTRAINT CK_Payments_PaymentStatus CHECK (PaymentStatus IN (N'Paid', N'Refunded')),
    PaidAt          DATETIME2(0)  NOT NULL
);

CREATE TABLE dbo.Results (
    ResultId        INT IDENTITY(1,1) CONSTRAINT PK_Results PRIMARY KEY,
    RegistrationId  INT NOT NULL CONSTRAINT FK_Results_Registrations REFERENCES dbo.Registrations (RegistrationId)
                        CONSTRAINT UQ_Results_RegistrationId UNIQUE,
    Score           DECIMAL(5,2) NOT NULL,
    Award           NVARCHAR(20) NULL
        CONSTRAINT CK_Results_Award CHECK (Award IN (N'Gold', N'Silver', N'Bronze', N'Merit')),
    PublishedAt     DATETIME2(0) NOT NULL
);
GO
