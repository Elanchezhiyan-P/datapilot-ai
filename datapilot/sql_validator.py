import sqlglot
from pydantic import BaseModel
from sqlglot import exp
from sqlglot.errors import ParseError

DEFAULT_SCHEMA = "dbo"

# Top-level statements we accept: SELECT, or UNION / INTERSECT / EXCEPT of SELECTs.
_ALLOWED_STATEMENTS = (exp.Select, exp.SetOperation)

# Nodes that must not appear anywhere in the tree, even nested inside a SELECT or CTE.
_FORBIDDEN_NODES = tuple(
    node
    for node in (
        getattr(exp, name, None)
        for name in (
            "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter",
            "TruncateTable", "Command", "Execute", "Grant", "Revoke", "Declare",
            "Into", "Set", "Use",
        )
    )
    if node is not None
)

# Functions that reach outside the database.
_FORBIDDEN_FUNCTIONS = {"OPENROWSET", "OPENQUERY", "OPENDATASOURCE", "OPENXML"}


class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str]
    tables: list[str]


def _parse(sql: str) -> list[exp.Expression]:
    return [statement for statement in sqlglot.parse(sql, dialect="tsql") if statement]


def _table_name(table: exp.Table) -> str:
    schema = table.db or DEFAULT_SCHEMA
    return f"{schema}.{table.name}".lower()


def _check_tables(tree: exp.Expression, allowed: set[str], errors: list[str]) -> list[str]:
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables: set[str] = set()

    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            errors.append("Table-valued functions are not allowed.")
            continue
        if not table.db and table.name.lower() in cte_names:
            continue
        if table.catalog:
            errors.append(f"Cross-database access is not allowed: {table.sql(dialect='tsql')}")
            continue

        name = _table_name(table)
        tables.add(name)
        if name not in allowed:
            errors.append(f"Table is not allowed: {name}")

    return sorted(tables)


def validate_sql(sql: str, allowed_tables: set[str]) -> ValidationResult:
    allowed = {name.lower() for name in allowed_tables}
    errors: list[str] = []

    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, errors=["SQL is empty."], tables=[])

    try:
        statements = _parse(sql)
    except ParseError as e:
        return ValidationResult(
            is_valid=False, errors=[f"SQL could not be parsed: {e}"], tables=[]
        )

    if len(statements) != 1:
        return ValidationResult(
            is_valid=False,
            errors=[f"Exactly one statement is allowed, found {len(statements)}."],
            tables=[],
        )

    tree = statements[0]

    if not isinstance(tree, _ALLOWED_STATEMENTS):
        errors.append(f"Only SELECT statements are allowed, found {type(tree).__name__}.")

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            errors.append(f"Forbidden operation: {type(node).__name__}.")
        elif isinstance(node, exp.Anonymous) and node.name.upper() in _FORBIDDEN_FUNCTIONS:
            errors.append(f"Forbidden function: {node.name.upper()}.")

    tables = _check_tables(tree, allowed, errors)

    unique_errors = list(dict.fromkeys(errors))
    return ValidationResult(is_valid=not unique_errors, errors=unique_errors, tables=tables)
