from datapilot.grounding import extract_numbers, ungrounded_numbers


def test_extracts_plain_comma_and_decimal_numbers() -> None:
    assert extract_numbers("409 students, 1,398 registrations, 65.13%") == ["409", "1398", "65.13"]


def test_ignores_numbers_glued_to_letters() -> None:
    assert extract_numbers("Q3 was 1st") == []


def test_number_from_result_is_grounded() -> None:
    assert ungrounded_numbers("There are 409 students.", [{"rows": [{"n": 409}]}]) == []


def test_rounded_number_is_grounded() -> None:
    result = {"rows": [{"AverageScore": 65.1283482142857}]}
    assert ungrounded_numbers("The average was 65.13.", [result]) == []
    assert ungrounded_numbers("The average was 65.1.", [result]) == []


def test_invented_number_is_flagged() -> None:
    assert ungrounded_numbers("There are 512 students.", [{"rows": [{"n": 409}]}]) == ["512"]


def test_mental_arithmetic_is_flagged() -> None:
    # 2243 - 1802 = 441 was never returned by a query.
    result = {"rows": [{"y": 2025, "n": 1802}, {"y": 2026, "n": 2243}]}
    assert ungrounded_numbers("2026 had 441 more registrations.", [result]) == ["441"]


def test_numbers_from_the_question_are_allowed() -> None:
    assert ungrounded_numbers("In 2026 there were 156.", [{"n": 156}, "absent in 2026?"]) == []


def test_numbers_inside_text_values_count() -> None:
    assert ungrounded_numbers("Level 5-6 had the most.", [{"rows": [{"LevelName": "Level 5-6"}]}]) == []
