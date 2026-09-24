from typing import Any

import pyodbc

from datapilot.config import Settings, get_settings

LOGIN_TIMEOUT_SECONDS = 5
QUERY_TIMEOUT_SECONDS = 30


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
