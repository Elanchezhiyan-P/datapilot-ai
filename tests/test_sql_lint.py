from datapilot.schema import ColumnInfo, DatabaseSchema, ForeignKeyInfo, TableInfo
from datapilot.sql_lint import check_joins


def _column(name: str) -> ColumnInfo:
    return ColumnInfo(name=name, data_type="INT", is_nullable=False, is_identity=False)


SCHEMA = DatabaseSchema(
    database_name="Test",
    tables=[
        TableInfo(schema_name="dbo", name="Schools", columns=[_column("SchoolId")]),
        TableInfo(
            schema_name="dbo", name="Students",
            columns=[_column("StudentId"), _column("SchoolId")],
            foreign_keys=[ForeignKeyInfo(column="SchoolId", references_table="dbo.Schools",
                                         references_column="SchoolId")],
        ),
        TableInfo(
            schema_name="dbo", name="Registrations",
            columns=[_column("RegistrationId"), _column("StudentId")],
            foreign_keys=[ForeignKeyInfo(column="StudentId", references_table="dbo.Students",
                                         references_column="StudentId")],
        ),
    ],
)


def test_foreign_key_join_is_accepted() -> None:
    sql = ("SELECT COUNT(*) FROM dbo.Registrations r JOIN dbo.Students s ON r.StudentId = s.StudentId "
           "JOIN dbo.Schools sc ON sc.SchoolId = s.SchoolId")
    assert check_joins(sql, SCHEMA) == []


def test_join_on_unrelated_columns_is_flagged() -> None:
    sql = "SELECT COUNT(*) FROM dbo.Registrations AS T1 JOIN dbo.Schools AS T3 ON T1.StudentId = T3.SchoolId"
    problems = check_joins(sql, SCHEMA)
    assert len(problems) == 1
    assert "T1.StudentId = T3.SchoolId" in problems[0]


def test_filters_inside_on_are_ignored() -> None:
    sql = "SELECT * FROM dbo.Students s JOIN dbo.Schools sc ON sc.SchoolId = s.SchoolId AND s.StudentId = 5"
    assert check_joins(sql, SCHEMA) == []
