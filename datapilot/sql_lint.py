"""Correctness checks on SQL that is already known to be safe.

Unlike sql_validator (security: must never be bypassed), these catch likely-wrong
queries and tell the model how to fix them. Currently: joins must follow a foreign key.
"""
import sqlglot
from sqlglot import exp

from datapilot.schema import DatabaseSchema
from datapilot.sql_validator import DEFAULT_SCHEMA


def _foreign_key_pairs(schema: DatabaseSchema) -> set[frozenset[str]]:
    pairs = set()
    for table in schema.tables:
        for fk in table.foreign_keys:
            pairs.add(frozenset({
                f"{table.full_name}.{fk.column}".lower(),
                f"{fk.references_table}.{fk.references_column}".lower(),
            }))
    return pairs


def check_joins(sql: str, schema: DatabaseSchema) -> list[str]:
    """Problems with JOIN conditions that do not match any foreign key."""
    try:
        tree = sqlglot.parse_one(sql, dialect="tsql")
    except sqlglot.errors.ParseError:
        return []

    aliases = {
        table.alias_or_name.lower(): f"{table.db or DEFAULT_SCHEMA}.{table.name}".lower()
        for table in tree.find_all(exp.Table)
    }
    valid = _foreign_key_pairs(schema)
    problems = []

    for join in tree.find_all(exp.Join):
        condition = join.args.get("on")
        if condition is None:
            continue
        for equality in condition.find_all(exp.EQ):
            left, right = equality.left, equality.right
            if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
                continue
            if not (left.table and right.table):
                continue
            left_table = aliases.get(left.table.lower())
            right_table = aliases.get(right.table.lower())
            if not left_table or not right_table or left_table == right_table:
                continue
            pair = frozenset({f"{left_table}.{left.name}".lower(), f"{right_table}.{right.name}".lower()})
            if pair not in valid:
                problems.append(f"Join condition {equality.sql(dialect='tsql')} does not match "
                                "any foreign key.")
    return problems
