from dataclasses import dataclass
from typing import Any

import pyodbc

from datapilot.config import Settings, get_settings

LOGIN_TIMEOUT_SECONDS = 5
QUERY_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ROWS = 1000


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


class DatabaseError(Exception):
    """Raised when a database operation fails."""


def _odbc_value(value: str) -> str:
    # Braces let values contain ';' or '='; a literal '}' is escaped as '}}'.
    return "{" + value.replace("}", "}}") + "}"


def _build_connection_string(settings: Settings) -> str:
    parts = {
        "DRIVER": _odbc_value(settings.db_driver),
        "SERVER": settings.db_server,
        "DATABASE": settings.db_name,
        "UID": _odbc_value(settings.db_user),
        "PWD": _odbc_value(settings.db_password),
        "Encrypt": "yes",
        "TrustServerCertificate": "yes" if settings.db_trust_server_certificate else "no",
    }
    return ";".join(f"{key}={value}" for key, value in parts.items())


def get_connection() -> pyodbc.Connection:
    settings = get_settings()

    try:
        connection = pyodbc.connect(
            _build_connection_string(settings), timeout=LOGIN_TIMEOUT_SECONDS
        )
    except pyodbc.Error as e:
        # Never include the connection string here: it contains the password.
        raise DatabaseError(
            f"Could not connect to {settings.db_server}/{settings.db_name}: {e}"
        ) from e

    connection.timeout = QUERY_TIMEOUT_SECONDS
    return connection


def run_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(sql, *params)

        if cursor.description is None:
            return []

        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except pyodbc.Error as e:
        raise DatabaseError(f"Query failed: {e}") from e
    finally:
        connection.close()


def run_readonly_query(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> QueryResult:
    """Run already-validated SQL and return at most max_rows rows.

    "Read-only" is enforced by the database login and the SQL validator,
    not by this function. Always validate the SQL before calling it.
    """
    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(sql)

        if cursor.description is None:
            return QueryResult(columns=[], rows=[], truncated=False)

        columns = [column[0] for column in cursor.description]
        # Fetch one extra row: if it arrives, the result was cut off.
        fetched = cursor.fetchmany(max_rows + 1)
        rows = [dict(zip(columns, row)) for row in fetched[:max_rows]]
        return QueryResult(columns=columns, rows=rows, truncated=len(fetched) > max_rows)
    except pyodbc.Error as e:
        raise DatabaseError(f"Query failed: {e}") from e
    finally:
        connection.close()
