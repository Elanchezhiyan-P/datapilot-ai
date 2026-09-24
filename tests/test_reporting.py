from datapilot.reporting import render_html, suggest_chart, summarize, to_csv


def test_single_value_gets_no_chart() -> None:
    chart = suggest_chart("How many?", ["n"], [{"n": 3000}])
    assert chart.type == "none"


def test_categories_get_a_bar_chart_sorted_largest_first() -> None:
    rows = [{"City": "Chennai", "Students": 380}, {"City": "Madurai", "Students": 408}]
    chart = suggest_chart("Students per city", ["City", "Students"], rows)

    assert chart.type == "bar"
    assert [(p.label, p.value) for p in chart.points] == [("Madurai", 408), ("Chennai", 380)]


def test_bar_and_line_render_with_whole_number_ticks() -> None:
    # Regression: large integer tick values crashed on Python < 3.12.
    bars = [{"Method": "UPI", "Total": 585000}, {"Method": "Cash", "Total": 60500}]
    line = [{"Month": m, "N": n} for m, n in [(1, 883), (2, 793), (3, 266)]]
    for columns, rows in [(["Method", "Total"], bars), (["Month", "N"], line)]:
        chart = suggest_chart("q", columns, rows)
        page = render_html("q", "a", None, columns, rows, chart, summarize(columns, rows))
        assert "<svg" in page


def test_year_and_month_become_one_sorted_time_axis() -> None:
    rows = [
        {"RegistrationYear": 2026, "RegistrationMonth": 1, "Registrations": 883},
        {"RegistrationYear": 2025, "RegistrationMonth": 12, "Registrations": 301},
        {"RegistrationYear": 2026, "RegistrationMonth": 2, "Registrations": 793},
    ]
    chart = suggest_chart("Monthly", list(rows[0]), rows)

    assert chart.type == "line"
    assert chart.y_label == "Registrations"
    assert [p.label for p in chart.points] == ["2025-12", "2026-01", "2026-02"]


def test_decimal_strings_count_as_numbers() -> None:
    rows = [{"School": "A", "AvgPct": "65.13"}, {"School": "B", "AvgPct": "63.10"}]
    assert suggest_chart("Avg", ["School", "AvgPct"], rows).points[0].value == 65.13


def test_ids_are_not_plotted_as_measures() -> None:
    rows = [{"StudentId": 1, "FirstName": "A"}, {"StudentId": 2, "FirstName": "B"}]
    assert suggest_chart("List", ["StudentId", "FirstName"], rows).type == "none"


def test_summary_statistics() -> None:
    summary = summarize(["n", "city"], [{"n": 2, "city": "X"}, {"n": 4, "city": None}])

    assert summary[0].kind == "number" and summary[0].total == 6 and summary[0].mean == 3
    assert summary[1].kind == "text" and summary[1].nulls == 1


def test_csv_has_header_and_rows() -> None:
    assert to_csv(["a", "b"], [{"a": 1, "b": "x"}]).splitlines() == ["a,b", "1,x"]


def test_html_escapes_values_from_the_data() -> None:
    rows = [{"Name": "<script>alert(1)</script>", "n": 1}, {"Name": "B", "n": 2}]
    chart = suggest_chart("q", ["Name", "n"], rows)
    page = render_html("q", "answer", "SELECT 1", ["Name", "n"], rows, chart, summarize(["Name", "n"], rows))

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
