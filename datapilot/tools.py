"""Tools Gemini may request. Gemini never runs these itself: it asks, we run them.

Each tool returns a JSON-serialisable dict. Failures are returned as {"error": ...}
instead of raised, so the model can read what went wrong and try again.
"""
import json
from typing import Any, Callable

from google.genai import types

from datapilot.database import DatabaseError, run_readonly_query
from datapilot.schema import DatabaseSchema, TableInfo, format_schema_for_prompt
from datapilot.sql_lint import check_joins
from datapilot.sql_validator import validate_sql

MAX_ROWS_FOR_MODEL = 50

DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_database_schema",
        description=(
            "List every table in the database with its column names. "
            "Call this first to find out which tables exist."
        ),
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="get_table_schema",
        description=(
            "Get full details for one table: column types, primary key, "
            "foreign keys and the allowed values of coded columns such as Status."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Schema-qualified table name, e.g. 'dbo.Students'.",
                }
            },
            "required": ["table_name"],
        },
    ),
    types.FunctionDeclaration(
        name="get_relationships",
        description="List every foreign key relationship, i.e. how tables join.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="execute_readonly_sql",
        description=(
            "Run one read-only T-SQL SELECT statement and return the rows. "
            "The query is safety-checked first; unsafe queries are rejected. "
            f"At most {MAX_ROWS_FOR_MODEL} rows are returned."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A single T-SQL SELECT statement."}
            },
            "required": ["query"],
        },
    ),
    types.FunctionDeclaration(
        name="get_distinct_values",
        description=(
            "Show the most common values of one column with their row counts. "
            "Use it to check real filter values (e.g. how a city is spelled) "
            "before filtering on them."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "e.g. 'dbo.Schools'."},
                "column_name": {"type": "string", "description": "e.g. 'City'."},
            },
            "required": ["table_name", "column_name"],
        },
    ),
]

DISTINCT_VALUES_LIMIT = 50


def _json_safe(value: Any) -> Any:
    # Decimal, date and datetime are not JSON types; round-trip through text.
    return json.loads(json.dumps(value, default=str))


class ToolBox:
    """The tools, bound to one discovered schema."""

    def __init__(self, schema: DatabaseSchema, schema_in_context: bool = False) -> None:
        self.schema = schema
        # When the schema is already in the prompt, there is nothing to look up first.
        self._schema_looked_up = schema_in_context
        self._tables = {table.full_name.lower(): table for table in schema.tables}
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "get_database_schema": self.get_database_schema,
            "get_table_schema": self.get_table_schema,
            "get_relationships": self.get_relationships,
            "execute_readonly_sql": self.execute_readonly_sql,
            "get_distinct_values": self.get_distinct_values,
        }

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}. Available: {sorted(self._handlers)}"}
        try:
            return handler(**args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}

    def get_database_schema(self) -> dict[str, Any]:
        self._schema_looked_up = True
        return {
            "database": self.schema.database_name,
            "tables": {
                table.full_name: [column.name for column in table.columns]
                for table in self.schema.tables
            },
        }

    def _find_table(self, table_name: str) -> TableInfo | None:
        name = table_name if "." in table_name else f"dbo.{table_name}"
        return self._tables.get(name.lower())

    def get_table_schema(self, table_name: str) -> dict[str, Any]:
        table = self._find_table(table_name)
        if table is None:
            return {"error": f"No table named {table_name}. Call get_database_schema."}
        self._schema_looked_up = True
        single = DatabaseSchema(database_name=self.schema.database_name, tables=[table])
        return {"table": table.full_name, "definition": format_schema_for_prompt(single)}

    def get_relationships(self) -> dict[str, Any]:
        return {
            "relationships": [
                f"{table.full_name}.{fk.column} -> {fk.references_table}.{fk.references_column}"
                for table in self.schema.tables
                for fk in table.foreign_keys
            ]
        }

    def execute_readonly_sql(self, query: str) -> dict[str, Any]:
        # The security boundary: this runs no matter what the model asked for.
        validation = validate_sql(query, self.schema.table_names())
        if not validation.is_valid:
            return {"error": "Query rejected by safety checks.", "details": validation.errors}

        join_problems = check_joins(query, self.schema)
        if join_problems:
            return {"error": "Likely wrong join.", "details": join_problems,
                    "valid_joins": self.get_relationships()["relationships"]}

        # Refuse SQL until the model has looked at the schema.
        if not self._schema_looked_up:
            return {"error": "Look up the schema first with get_database_schema or "
                             "get_table_schema, then write the query using real column names."}

        try:
            result = run_readonly_query(query, max_rows=MAX_ROWS_FOR_MODEL)
        except DatabaseError as e:
            return {"error": str(e),
                    "hint": "Check column names and allowed values with get_table_schema, "
                            "then fix the query and try again."}

        return {
            "columns": result.columns,
            "rows": _json_safe(result.rows),
            "row_count": len(result.rows),
            "truncated": result.truncated,
        }

    def get_distinct_values(self, table_name: str, column_name: str) -> dict[str, Any]:
        table = self._find_table(table_name)
        if table is None:
            return {"error": f"No table named {table_name}. Call get_database_schema."}
        column = next((c for c in table.columns if c.name.lower() == column_name.lower()), None)
        if column is None:
            return {"error": f"{table.full_name} has no column {column_name}."}

        # Identifiers come from the discovered schema, never from the model's text,
        # so building the SQL with them is safe.
        query = (
            f"SELECT TOP ({DISTINCT_VALUES_LIMIT}) [{column.name}] AS value, COUNT(*) AS row_count "
            f"FROM [{table.schema_name}].[{table.name}] "
            f"GROUP BY [{column.name}] ORDER BY COUNT(*) DESC"
        )
        try:
            result = run_readonly_query(query, max_rows=DISTINCT_VALUES_LIMIT)
        except DatabaseError as e:
            return {"error": str(e)}

        self._schema_looked_up = True
        return {"table": table.full_name, "column": column.name,
                "values": _json_safe(result.rows), "truncated": result.truncated}
