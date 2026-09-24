import re

from pydantic import BaseModel

from datapilot.database import run_query

_COLUMNS_SQL = """
SELECT
    s.name  AS schema_name,
    t.name  AS table_name,
    c.name  AS column_name,
    ty.name AS type_name,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable,
    c.is_identity
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE t.is_ms_shipped = 0
ORDER BY s.name, t.name, c.column_id
"""

_PRIMARY_KEYS_SQL = """
SELECT
    OBJECT_SCHEMA_NAME(kc.parent_object_id) AS schema_name,
    OBJECT_NAME(kc.parent_object_id)        AS table_name,
    COL_NAME(ic.object_id, ic.column_id)    AS column_name
FROM sys.key_constraints kc
JOIN sys.index_columns ic
    ON ic.object_id = kc.parent_object_id
   AND ic.index_id = kc.unique_index_id
WHERE kc.type = 'PK'
"""

_FOREIGN_KEYS_SQL = """
SELECT
    OBJECT_SCHEMA_NAME(fkc.parent_object_id)                     AS schema_name,
    OBJECT_NAME(fkc.parent_object_id)                            AS table_name,
    COL_NAME(fkc.parent_object_id, fkc.parent_column_id)         AS column_name,
    OBJECT_SCHEMA_NAME(fkc.referenced_object_id)                 AS ref_schema_name,
    OBJECT_NAME(fkc.referenced_object_id)                        AS ref_table_name,
    COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS ref_column_name
FROM sys.foreign_key_columns fkc
ORDER BY schema_name, table_name, column_name
"""

_CHECK_CONSTRAINTS_SQL = """
SELECT
    OBJECT_SCHEMA_NAME(cc.parent_object_id)            AS schema_name,
    OBJECT_NAME(cc.parent_object_id)                   AS table_name,
    COL_NAME(cc.parent_object_id, cc.parent_column_id) AS column_name,
    cc.definition
FROM sys.check_constraints cc
WHERE cc.parent_column_id <> 0
"""

# SQL Server stores CHECK (Status IN ('A', 'B')) as ([Status]=N'A' OR [Status]=N'B').
_ALLOWED_VALUES_CHECK = re.compile(r"\((\[\w+\]=N?'[^']*')( OR \[\w+\]=N?'[^']*')*\)")
_QUOTED_VALUE = re.compile(r"=N?'([^']*)'")

_TYPES_WITH_LENGTH = {"char", "varchar", "binary", "varbinary"}
_UNICODE_TYPES_WITH_LENGTH = {"nchar", "nvarchar"}
_TYPES_WITH_PRECISION = {"decimal", "numeric"}


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    is_identity: bool
    is_primary_key: bool = False
    allowed_values: list[str] | None = None
    check_definition: str | None = None


class ForeignKeyInfo(BaseModel):
    column: str
    references_table: str
    references_column: str


class TableInfo(BaseModel):
    schema_name: str
    name: str
    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKeyInfo] = []

    @property
    def full_name(self) -> str:
        return f"{self.schema_name}.{self.name}"

    def column(self, name: str) -> ColumnInfo:
        return next(c for c in self.columns if c.name == name)


class DatabaseSchema(BaseModel):
    database_name: str
    tables: list[TableInfo]

    def table_names(self) -> set[str]:
        return {table.full_name for table in self.tables}


def _format_type(row: dict) -> str:
    type_name = row["type_name"]
    max_length = row["max_length"]

    if type_name in _TYPES_WITH_LENGTH:
        length = "MAX" if max_length == -1 else str(max_length)
        return f"{type_name.upper()}({length})"
    if type_name in _UNICODE_TYPES_WITH_LENGTH:
        # sys.columns.max_length is in bytes; NCHAR/NVARCHAR use 2 bytes per character.
        length = "MAX" if max_length == -1 else str(max_length // 2)
        return f"{type_name.upper()}({length})"
    if type_name in _TYPES_WITH_PRECISION:
        return f"{type_name.upper()}({row['precision']},{row['scale']})"
    return type_name.upper()


def discover_schema() -> DatabaseSchema:
    tables: dict[tuple[str, str], TableInfo] = {}

    for row in run_query(_COLUMNS_SQL):
        key = (row["schema_name"], row["table_name"])
        if key not in tables:
            tables[key] = TableInfo(schema_name=key[0], name=key[1], columns=[])
        tables[key].columns.append(
            ColumnInfo(
                name=row["column_name"],
                data_type=_format_type(row),
                is_nullable=row["is_nullable"],
                is_identity=row["is_identity"],
            )
        )

    for row in run_query(_PRIMARY_KEYS_SQL):
        table = tables[(row["schema_name"], row["table_name"])]
        table.column(row["column_name"]).is_primary_key = True

    for row in run_query(_FOREIGN_KEYS_SQL):
        table = tables[(row["schema_name"], row["table_name"])]
        table.foreign_keys.append(
            ForeignKeyInfo(
                column=row["column_name"],
                references_table=f"{row['ref_schema_name']}.{row['ref_table_name']}",
                references_column=row["ref_column_name"],
            )
        )

    for row in run_query(_CHECK_CONSTRAINTS_SQL):
        definition = row["definition"]
        if definition is None:
            # The login lacks VIEW DEFINITION, so SQL Server hides the constraint text.
            continue

        column = tables[(row["schema_name"], row["table_name"])].column(row["column_name"])
        if _ALLOWED_VALUES_CHECK.fullmatch(definition):
            column.allowed_values = sorted(_QUOTED_VALUE.findall(definition))
        else:
            column.check_definition = definition

    database_name = run_query("SELECT DB_NAME() AS name")[0]["name"]
    return DatabaseSchema(database_name=database_name, tables=list(tables.values()))


def format_schema_for_prompt(schema: DatabaseSchema) -> str:
    lines: list[str] = []

    for table in schema.tables:
        foreign_keys = {fk.column: fk for fk in table.foreign_keys}
        lines.append(table.full_name)

        for column in table.columns:
            parts = [column.name, column.data_type]
            if column.is_primary_key:
                parts.append("PK")
            elif not column.is_nullable:
                parts.append("NOT NULL")
            if column.name in foreign_keys:
                fk = foreign_keys[column.name]
                parts.append(f"FK -> {fk.references_table}.{fk.references_column}")
            if column.allowed_values:
                values = ", ".join(f"'{v}'" for v in column.allowed_values)
                parts.append(f"VALUES ({values})")
            if column.check_definition:
                parts.append(f"CHECK {column.check_definition}")
            lines.append("  " + " ".join(parts))

        lines.append("")

    return "\n".join(lines).rstrip()
