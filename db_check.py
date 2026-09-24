import sys

from datapilot.config import ConfigError
from datapilot.database import DatabaseError, run_query


def main() -> None:
    try:
        version = run_query("SELECT @@VERSION AS version")
        print(version[0]["version"].splitlines()[0])

        schools = run_query(
            """
            SELECT sc.SchoolName, COUNT(*) AS StudentCount
            FROM dbo.Students s
            JOIN dbo.Schools sc ON sc.SchoolId = s.SchoolId
            WHERE sc.City = ?
            GROUP BY sc.SchoolName
            ORDER BY sc.SchoolName
            """,
            ("Coimbatore",),
        )
        print("\nStudents per school in Coimbatore:")
        for school in schools:
            print(f"  {school['SchoolName']}: {school['StudentCount']}")
    except (ConfigError, DatabaseError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nSecurity check: attempting an INSERT (should be refused)...")
    try:
        run_query(
            "INSERT INTO dbo.Schools (SchoolName, City, State, SchoolType) VALUES (?, ?, ?, ?)",
            ("Test School", "Test City", "Test State", "Private"),
        )
        print("WARNING: INSERT was accepted. The login is NOT read-only!")
    except DatabaseError as e:
        print(f"Blocked as expected: {e}")


if __name__ == "__main__":
    main()
