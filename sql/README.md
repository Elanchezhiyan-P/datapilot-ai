# Database setup

These scripts build the `DataPilotLab` database that DataPilot answers questions about:
six related tables of school exam data, filled with the same sample data every time.

| Script | What it does | Re-runnable? |
|---|---|---|
| `00_create_database.sql` | Creates the `DataPilotLab` database | Yes: skips if it exists |
| `01_create_tables.sql` | Creates the six tables with keys and `CHECK` constraints | **Drops and recreates the tables, deleting their data** |
| `02_seed_data.sql` | Fills the tables with sample data | Yes: empties the tables first, restarts IDs at 1 |
| `03_create_readonly_login.sql` | Creates the `datapilot_reader` login DataPilot connects with | Yes |
| `04_verify_setup.sql` | Checks row counts and the reader's permissions; changes nothing | Yes |

Run them in order with an **admin** login (for example your Windows login in SSMS).

## Before you start (one-time server settings)

These are server settings, so they are done by hand rather than in a script:

1. **Mixed-mode authentication.** DataPilot logs in with a SQL login, not Windows
   authentication (Windows logins don't work from Linux/WSL). In SSMS: right-click the
   server → *Properties* → *Security* → **SQL Server and Windows Authentication mode**.
2. **TCP/IP.** In *SQL Server Configuration Manager* → *SQL Server Network
   Configuration* → *Protocols*, enable **TCP/IP** (port 1433).
3. **Restart the SQL Server service** after changing either.

## Run the scripts

**In SSMS:** open each file in order and press *Execute* (F5). Before `03`, replace
`<choose-a-strong-password>` with a real password.

**With sqlcmd** (from the project folder, Windows authentication, trusting the local
server's certificate):

```bash
sqlcmd -S localhost -E -C -b -i sql/00_create_database.sql -i sql/01_create_tables.sql -i sql/02_seed_data.sql
```
Edit the password in `sql/03_create_readonly_login.sql`, then:
```bash
sqlcmd -S localhost -E -C -b -i sql/03_create_readonly_login.sql -i sql/04_verify_setup.sql
```

The last script should print `PASS` on every line and `All checks passed.`

Then put the same login details in `.env`:

```text
DB_SERVER=localhost          # from WSL: <windows-hostname>.local
DB_NAME=DataPilotLab
DB_USER=datapilot_reader
DB_PASSWORD=<the password from 03>
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUST_SERVER_CERTIFICATE=yes   # only for a local server with a self-signed certificate
```

## The data

| Table | Rows | Notes |
|---|---|---|
| `Schools` | 40 | 8 cities × 5 schools (Private, Government, Aided) |
| `Students` | 3,000 | Grades 1–12 as of 2026; the city comes from the school |
| `Exams` | 18 | 2024–2026 × 6 levels. Levels 1–4 are out of 96 points, the rest out of 120 |
| `Registrations` | 5,443 | Status `Completed`, `Absent` or `Cancelled`; participation grows each year |
| `Payments` | 5,443 | One per registration; cancelled ones are refunded |
| `Results` | 4,886 | Completed registrations only; awards Gold, Silver, Bronze, Merit |

The rows are generated from hashes, not random numbers, so every run produces
**exactly the same data**. That matters: the evaluation benchmark and the examples in the
main README (such as "409 students attend schools in Coimbatore") depend on it. The
scripts were checked by building a fresh copy and comparing a checksum of every table
with an existing `DataPilotLab`: all six matched.

Some details are deliberate traps for text-to-SQL, to see whether DataPilot copes:
the city is on `Schools`, not `Students` (needs a join); averaging raw scores across
levels is wrong because the maximum score differs (use `Score * 100.0 / MaxScore`);
and "participants" can mean all registrations or only completed ones.

## Why the read-only login matters

`datapilot_reader` is a member of `db_datareader` only, so SQL Server itself refuses any
write, even if DataPilot's own SQL validator had a bug. It also has `VIEW DEFINITION`,
which lets schema discovery read the text of `CHECK` constraints (the allowed values of
columns like `Status`); that grants metadata access only, not extra data or writes.
`04_verify_setup.sql` proves both by acting as the login.
