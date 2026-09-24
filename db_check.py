import sys

from datapilot.config import ConfigError
from datapilot.database import DatabaseError, run_query


def main() -> None:
    try:
        version = run_query("SELECT @@VERSION AS version")
        print(version[0]["version"].splitlines()[0])

        students = run_query(
            "SELECT FullName, Grade FROM dbo.Students WHERE City = ?",
            ("Coimbatore",),
        )
        print(f"\nStudents in Coimbatore: {len(students)}")
        for student in students:
            print(f"  {student['FullName']} (grade {student['Grade']})")
    except (ConfigError, DatabaseError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nSecurity check: attempting an INSERT (should be refused)...")
    try:
        run_query(
            "INSERT INTO dbo.Students (FullName, City, Grade) VALUES (?, ?, ?)",
            ("Test Student", "Test City", 1),
        )
        print("WARNING: INSERT was accepted. The login is NOT read-only!")
    except DatabaseError as e:
        print(f"Blocked as expected: {e}")


if __name__ == "__main__":
    main()
