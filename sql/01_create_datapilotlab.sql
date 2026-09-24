/*
    DataPilotLab: schema + deterministic seed data.

    Run in SSMS with an ADMIN login (not datapilot_reader).
    WARNING: drops and recreates every DataPilotLab table.

    The data is generated from hashes, not random numbers, so every run
    produces exactly the same rows. That keeps evaluation results reproducible.
*/
USE DataPilotLab;
GO

SET NOCOUNT ON;

DROP TABLE IF EXISTS dbo.Results, dbo.Payments, dbo.Registrations, dbo.Exams, dbo.Students, dbo.Schools;
DROP FUNCTION IF EXISTS dbo.SeedHash;
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

-- Temporary helper: deterministic pseudo-random non-negative INT from a text key.
CREATE FUNCTION dbo.SeedHash (@key NVARCHAR(200))
RETURNS INT
WITH SCHEMABINDING
AS
BEGIN
    RETURN CAST(CAST(HASHBYTES('MD5', @key) AS BINARY(4)) AS INT) & 2147483647;
END;
GO

------------------------------------------------------------------------------
-- Seed data
------------------------------------------------------------------------------
SET NOCOUNT ON;

-- Schools: 8 cities x 5 school names = 40 schools
DECLARE @Cities TABLE (CityIdx INT PRIMARY KEY, City NVARCHAR(50), State NVARCHAR(50));
INSERT @Cities VALUES
    (0, N'Coimbatore',      N'Tamil Nadu'),
    (1, N'Chennai',         N'Tamil Nadu'),
    (2, N'Madurai',         N'Tamil Nadu'),
    (3, N'Tiruchirappalli', N'Tamil Nadu'),
    (4, N'Bengaluru',       N'Karnataka'),
    (5, N'Mysuru',          N'Karnataka'),
    (6, N'Kochi',           N'Kerala'),
    (7, N'Hyderabad',       N'Telangana');

DECLARE @SchoolNames TABLE (NameIdx INT PRIMARY KEY, BaseName NVARCHAR(100), SchoolType NVARCHAR(20));
INSERT @SchoolNames VALUES
    (0, N'Kendriya Vidyalaya',                N'Government'),
    (1, N'Green Valley Public School',        N'Private'),
    (2, N'St. Joseph''s Matriculation School', N'Aided'),
    (3, N'Sri Vidya Mandir',                  N'Private'),
    (4, N'National Model School',             N'Private');

INSERT dbo.Schools (SchoolName, City, State, SchoolType)
SELECT CONCAT(sn.BaseName, N', ', c.City), c.City, c.State, sn.SchoolType
FROM @Cities c
CROSS JOIN @SchoolNames sn
ORDER BY c.CityIdx, sn.NameIdx;

-- Students: 3,000, grades 1-12 as of 2026
DECLARE @FirstNames TABLE (Gender CHAR(1), Idx INT, Name NVARCHAR(50), PRIMARY KEY (Gender, Idx));
INSERT @FirstNames VALUES
    ('M', 0, N'Arun'),   ('M', 1, N'Karthik'), ('M', 2, N'Vignesh'), ('M', 3, N'Rahul'),
    ('M', 4, N'Surya'),  ('M', 5, N'Aditya'),  ('M', 6, N'Harish'),  ('M', 7, N'Pranav'),
    ('M', 8, N'Rohan'),  ('M', 9, N'Sanjay'),  ('M', 10, N'Nikhil'), ('M', 11, N'Varun'),
    ('F', 0, N'Priya'),  ('F', 1, N'Divya'),   ('F', 2, N'Kavya'),   ('F', 3, N'Ananya'),
    ('F', 4, N'Meera'),  ('F', 5, N'Lakshmi'), ('F', 6, N'Sneha'),   ('F', 7, N'Aishwarya'),
    ('F', 8, N'Nithya'), ('F', 9, N'Pooja'),   ('F', 10, N'Swathi'), ('F', 11, N'Harini');

DECLARE @LastNames TABLE (Idx INT PRIMARY KEY, Name NVARCHAR(50));
INSERT @LastNames VALUES
    (0, N'Kumar'), (1, N'Raman'),    (2, N'Iyer'),  (3, N'Nair'),
    (4, N'Reddy'), (5, N'Sharma'),   (6, N'Menon'), (7, N'Rao'),
    (8, N'Pillai'),(9, N'Subramanian'), (10, N'Krishnan'), (11, N'Gowda');

WITH Numbers AS (
    SELECT TOP (3000) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n
    FROM sys.all_objects a CROSS JOIN sys.all_objects b
),
Base AS (
    SELECT
        n,
        CASE WHEN dbo.SeedHash(CONCAT(N'gender-', n)) % 2 = 0 THEN 'M' ELSE 'F' END AS Gender,
        1 + dbo.SeedHash(CONCAT(N'grade-', n)) % 12 AS CurrentGrade
    FROM Numbers
)
INSERT dbo.Students (SchoolId, FirstName, LastName, Gender, DateOfBirth, CurrentGrade, CreatedAt)
SELECT
    1 + dbo.SeedHash(CONCAT(N'school-', b.n)) % 40,
    fn.Name,
    ln.Name,
    b.Gender,
    DATEFROMPARTS(2020 - b.CurrentGrade,
                  1 + dbo.SeedHash(CONCAT(N'dob-month-', b.n)) % 12,
                  1 + dbo.SeedHash(CONCAT(N'dob-day-', b.n)) % 28),
    b.CurrentGrade,
    DATEADD(DAY, dbo.SeedHash(CONCAT(N'created-', b.n)) % 180, CAST('2023-06-01' AS DATETIME2(0)))
FROM Base b
JOIN @FirstNames fn ON fn.Gender = b.Gender AND fn.Idx = dbo.SeedHash(CONCAT(N'first-', b.n)) % 12
JOIN @LastNames  ln ON ln.Idx = dbo.SeedHash(CONCAT(N'last-', b.n)) % 12
ORDER BY b.n;

-- Exams: 2024-2026 x 6 levels. Levels 1-4 are out of 96 points, the rest out of 120.
INSERT dbo.Exams (ExamYear, LevelName, MinGrade, MaxGrade, ExamDate, MaxScore)
SELECT
    y.ExamYear,
    CONCAT(N'Level ', l.MinGrade, N'-', l.MaxGrade),
    l.MinGrade,
    l.MaxGrade,
    DATEFROMPARTS(y.ExamYear, 3, 20),
    CASE WHEN l.MaxGrade <= 4 THEN 96 ELSE 120 END
FROM (VALUES (2024), (2025), (2026)) y (ExamYear)
CROSS JOIN (VALUES (1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)) l (MinGrade, MaxGrade)
ORDER BY y.ExamYear, l.MinGrade;

-- Registrations: a student's grade in an earlier year is CurrentGrade - (2026 - year).
-- Participation grows each year: 55% (2024), 65% (2025), 75% (2026).
WITH Candidates AS (
    SELECT s.StudentId, e.ExamId, e.ExamYear, e.ExamDate
    FROM dbo.Students s
    JOIN dbo.Exams e
        ON s.CurrentGrade - (2026 - e.ExamYear) BETWEEN e.MinGrade AND e.MaxGrade
)
INSERT dbo.Registrations (StudentId, ExamId, RegisteredAt, Status)
SELECT
    c.StudentId,
    c.ExamId,
    DATEADD(MINUTE, dbo.SeedHash(CONCAT(N'reg-minute-', c.StudentId, N'-', c.ExamId)) % 1440,
        DATEADD(DAY, -(10 + dbo.SeedHash(CONCAT(N'reg-day-', c.StudentId, N'-', c.ExamId)) % 80),
            CAST(c.ExamDate AS DATETIME2(0)))),
    CASE WHEN r.Roll < 90 THEN N'Completed'
         WHEN r.Roll < 97 THEN N'Absent'
         ELSE N'Cancelled' END
FROM Candidates c
CROSS APPLY (SELECT dbo.SeedHash(CONCAT(N'status-', c.StudentId, N'-', c.ExamId)) % 100 AS Roll) r
WHERE dbo.SeedHash(CONCAT(N'participates-', c.StudentId, N'-', c.ExamYear)) % 100
      < CASE c.ExamYear WHEN 2024 THEN 55 WHEN 2025 THEN 65 ELSE 75 END
ORDER BY c.ExamDate, c.StudentId;

-- Payments: one per registration; fee rises each year; cancelled registrations are refunded.
INSERT dbo.Payments (RegistrationId, Amount, PaymentMethod, PaymentStatus, PaidAt)
SELECT
    r.RegistrationId,
    CASE e.ExamYear WHEN 2024 THEN 400 WHEN 2025 THEN 450 ELSE 500 END,
    CASE WHEN m.Roll < 55 THEN N'UPI'
         WHEN m.Roll < 80 THEN N'Card'
         WHEN m.Roll < 95 THEN N'NetBanking'
         ELSE N'Cash' END,
    CASE WHEN r.Status = N'Cancelled' THEN N'Refunded' ELSE N'Paid' END,
    DATEADD(MINUTE, 5 + dbo.SeedHash(CONCAT(N'paid-', r.RegistrationId)) % 600, r.RegisteredAt)
FROM dbo.Registrations r
JOIN dbo.Exams e ON e.ExamId = r.ExamId
CROSS APPLY (SELECT dbo.SeedHash(CONCAT(N'method-', r.RegistrationId)) % 100 AS Roll) m
ORDER BY r.RegistrationId;

-- Results: only for completed registrations.
-- Percentage = student ability + school effect + per-exam noise, so school averages differ.
WITH Scored AS (
    SELECT
        r.RegistrationId,
        e.MaxScore,
        e.ExamDate,
        GREATEST(0, LEAST(100,
            20
            + dbo.SeedHash(CONCAT(N'ability-', s.StudentId)) % 55
            + dbo.SeedHash(CONCAT(N'school-bonus-', s.SchoolId)) % 15
            + dbo.SeedHash(CONCAT(N'noise-', r.RegistrationId)) % 21 - 10
        )) AS Pct
    FROM dbo.Registrations r
    JOIN dbo.Students s ON s.StudentId = r.StudentId
    JOIN dbo.Exams e ON e.ExamId = r.ExamId
    WHERE r.Status = N'Completed'
)
INSERT dbo.Results (RegistrationId, Score, Award, PublishedAt)
SELECT
    RegistrationId,
    ROUND(Pct * MaxScore / 100.0 * 4, 0) / 4,
    CASE WHEN Pct >= 90 THEN N'Gold'
         WHEN Pct >= 80 THEN N'Silver'
         WHEN Pct >= 70 THEN N'Bronze'
         WHEN Pct >= 60 THEN N'Merit' END,
    DATEADD(DAY, 45, CAST(ExamDate AS DATETIME2(0)))
FROM Scored
ORDER BY RegistrationId;
GO

DROP FUNCTION dbo.SeedHash;
GO

------------------------------------------------------------------------------
-- Summary
------------------------------------------------------------------------------
SELECT 'Schools' AS TableName, COUNT(*) AS [Rows] FROM dbo.Schools
UNION ALL SELECT 'Students',      COUNT(*) FROM dbo.Students
UNION ALL SELECT 'Exams',         COUNT(*) FROM dbo.Exams
UNION ALL SELECT 'Registrations', COUNT(*) FROM dbo.Registrations
UNION ALL SELECT 'Payments',      COUNT(*) FROM dbo.Payments
UNION ALL SELECT 'Results',       COUNT(*) FROM dbo.Results;
