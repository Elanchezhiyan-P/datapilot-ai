"""Reports: summary statistics, a chart suggestion, CSV and a self-contained HTML page.

The chart type is chosen by deterministic rules, not by the model: free, predictable
and testable. The API returns the ChartSpec as data so a future React frontend can
draw it; render_html() draws the same spec for local viewing and download.
"""
import csv
import html
import io
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

MAX_CHART_POINTS = 30
_TIME_NAME = re.compile(r"year|month|quarter|week|day|date", re.IGNORECASE)
_ID_NAME = re.compile(r"(^|_)id$|Id$")


class ColumnSummary(BaseModel):
    name: str
    kind: Literal["number", "text", "date", "empty"]
    count: int
    nulls: int
    distinct: int
    min: float | str | None = None
    max: float | str | None = None
    mean: float | None = None
    total: float | None = None


class ChartPoint(BaseModel):
    label: str
    value: float


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "none"]
    reason: str
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    points: list[ChartPoint] = []


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _is_date(value: Any) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    return isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T].*)?", value))


def _kind(values: list[Any]) -> str:
    present = [v for v in values if v is not None]
    if not present:
        return "empty"
    if all(_as_number(v) is not None for v in present):
        return "number"
    if all(_is_date(v) for v in present):
        return "date"
    return "text"


def summarize(columns: list[str], rows: list[dict[str, Any]]) -> list[ColumnSummary]:
    summaries = []
    for column in columns:
        values = [row.get(column) for row in rows]
        present = [v for v in values if v is not None]
        kind = _kind(values)
        summary = ColumnSummary(name=column, kind=kind, count=len(values),
                                nulls=len(values) - len(present),
                                distinct=len({str(v) for v in present}))
        if kind == "number":
            numbers = [_as_number(v) for v in present]
            summary.min, summary.max = min(numbers), max(numbers)
            summary.total = round(sum(numbers), 4)
            summary.mean = round(summary.total / len(numbers), 4)
        elif kind in ("text", "date") and present:
            texts = sorted(str(v) for v in present)
            summary.min, summary.max = texts[0], texts[-1]
        summaries.append(summary)
    return summaries


def _label_part(column: str, value: Any) -> str:
    if value is None:
        return "(none)"
    if "month" in column.lower() and _as_number(value) is not None and 1 <= float(value) <= 12:
        return f"{int(float(value)):02d}"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def suggest_chart(question: str, columns: list[str], rows: list[dict[str, Any]]) -> ChartSpec:
    if len(rows) < 2:
        return ChartSpec(type="none", reason="A single value reads best as a number, not a chart.")
    if len(rows) > MAX_CHART_POINTS:
        return ChartSpec(type="none", reason=f"More than {MAX_CHART_POINTS} rows: use the table.")

    kinds = {column: _kind([row.get(column) for row in rows]) for column in columns}
    # Years, months and ids are numbers but act as labels, never as the measure.
    label_like = {c for c in columns
                  if kinds[c] in ("text", "date") or _TIME_NAME.search(c) or _ID_NAME.search(c)}
    measures = [c for c in columns if kinds[c] == "number" and c not in label_like]
    labels = [c for c in columns if c in label_like and not _ID_NAME.search(c)]

    if not measures:
        return ChartSpec(type="none", reason="No numeric measure to plot.")
    if not labels:
        return ChartSpec(type="none", reason="No label column to plot against.")
    if len(measures) > 1:
        # One axis only: two measures of different scale never share a chart.
        reason_suffix = f" Plotting {measures[-1]}; other measures are in the table."
    else:
        reason_suffix = ""

    measure = measures[-1]
    is_time = any(_TIME_NAME.search(c) or kinds[c] == "date" for c in labels)
    points = [
        ChartPoint(label="-".join(_label_part(c, row.get(c)) for c in labels),
                   value=_as_number(row.get(measure)) or 0.0)
        for row in rows
    ]
    if is_time:
        points.sort(key=lambda p: p.label)
    else:
        # Categories have no natural order; largest first makes the comparison easy.
        points.sort(key=lambda p: p.value, reverse=True)

    chart_type = "line" if is_time and len(points) >= 3 else "bar"
    reason = ("Values over time: line chart." if chart_type == "line"
              else "Comparison across categories: bar chart.")
    return ChartSpec(type=chart_type, reason=reason + reason_suffix, title=question,
                     x_label=" / ".join(labels), y_label=measure, points=points)


def to_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _nice_ticks(maximum: float, count: int = 5) -> list[float]:
    if maximum <= 0:
        return [0.0, 1.0]
    raw_step = maximum / count
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw_step)
    return [i * step for i in range(int(math.ceil(maximum / step)) + 1)]


def _format_number(value: float) -> str:
    value = float(value)   # int.is_integer() only exists from Python 3.12
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _bar_svg(spec: ChartSpec) -> str:
    label_width, value_room, width = 260, 70, 760
    band, bar = 32, 20
    ticks = _nice_ticks(max(p.value for p in spec.points))
    top = ticks[-1]
    plot_width = width - label_width - value_room
    height = band * len(spec.points) + 36
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(spec.title)}">']
    for tick in ticks:
        x = label_width + plot_width * tick / top
        parts.append(f'<line class="grid" x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{height - 24}"/>')
        parts.append(f'<text class="tick" x="{x:.1f}" y="{height - 6}" text-anchor="middle">'
                     f'{_format_number(tick)}</text>')
    for index, point in enumerate(spec.points):
        y = index * band + (band - bar) / 2
        length = max(plot_width * point.value / top, 0)
        radius = min(4, length)
        # Rounded at the data end only; square where the bar meets the baseline.
        path = (f"M{label_width},{y} h{length - radius:.1f} a{radius},{radius} 0 0 1 {radius},{radius} "
                f"v{bar - 2 * radius} a{radius},{radius} 0 0 1 {-radius},{radius} h{-(length - radius):.1f} z")
        label, value = html.escape(point.label), _format_number(point.value)
        parts.append(
            f'<g class="mark" tabindex="0" data-label="{label}" data-value="{value}">'
            f'<rect class="hit" x="0" y="{index * band}" width="{width}" height="{band}"/>'
            f'<path class="bar" d="{path}"/>'
            f'<text class="label" x="{label_width - 10}" y="{y + bar / 2 + 4}" text-anchor="end">{label}</text>'
            f'<text class="value" x="{label_width + length + 8:.1f}" y="{y + bar / 2 + 4}">{value}</text>'
            f"</g>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _line_svg(spec: ChartSpec) -> str:
    width, height, left, right, top_pad, bottom = 760, 320, 64, 24, 16, 44
    ticks = _nice_ticks(max(p.value for p in spec.points))
    top = ticks[-1]
    plot_w, plot_h = width - left - right, height - top_pad - bottom
    count = len(spec.points)

    def x_of(i: int) -> float:
        return left + (plot_w * i / (count - 1) if count > 1 else plot_w / 2)

    def y_of(v: float) -> float:
        return top_pad + plot_h * (1 - v / top)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(spec.title)}">']
    for tick in ticks:
        y = y_of(tick)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">'
                     f'{_format_number(tick)}</text>')
    step = max(1, math.ceil(count / 12))
    for i, point in enumerate(spec.points):
        if i % step == 0 or i == count - 1:
            parts.append(f'<text class="tick" x="{x_of(i):.1f}" y="{height - bottom + 20}" '
                         f'text-anchor="middle">{html.escape(point.label)}</text>')
    coords = " ".join(f"{x_of(i):.1f},{y_of(p.value):.1f}" for i, p in enumerate(spec.points))
    parts.append(f'<polyline class="line" points="{coords}"/>')
    last = spec.points[-1]
    parts.append(f'<text class="value" x="{x_of(count - 1):.1f}" y="{y_of(last.value) - 12:.1f}" '
                 f'text-anchor="end">{_format_number(last.value)}</text>')
    parts.append(f'<line class="crosshair" x1="0" y1="{top_pad}" x2="0" y2="{height - bottom}"/>')
    for i, point in enumerate(spec.points):
        parts.append(f'<circle class="dot" cx="{x_of(i):.1f}" cy="{y_of(point.value):.1f}" r="4"/>')
    band = plot_w / max(count - 1, 1)
    for i, point in enumerate(spec.points):
        parts.append(
            f'<rect class="hit mark" tabindex="0" x="{x_of(i) - band / 2:.1f}" y="{top_pad}" '
            f'width="{band:.1f}" height="{plot_h}" data-x="{x_of(i):.1f}" '
            f'data-label="{html.escape(point.label)}" data-value="{_format_number(point.value)}"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


_STYLE = """
:root { color-scheme: light;
  --surface: #fcfcfb; --page: #f4f3f0; --text: #0b0b0b; --text-2: #52514e; --muted: #7a7974;
  --grid: #e6e5e0; --series: #2a78d6; --border: #dedcd5; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --surface: #1a1a19; --page: #111110; --text: #ffffff; --text-2: #c3c2b7; --muted: #929189;
  --grid: #2e2e2b; --series: #3987e5; --border: #34332f; } }
:root[data-theme="dark"] { color-scheme: dark;
  --surface: #1a1a19; --page: #111110; --text: #ffffff; --text-2: #c3c2b7; --muted: #929189;
  --grid: #2e2e2b; --series: #3987e5; --border: #34332f; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 32px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 15px; margin: 28px 0 8px; color: var(--text-2); }
.answer { font-size: 17px; margin: 12px 0 0; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.meta { color: var(--muted); font-size: 13px; }
svg { width: 100%; height: auto; display: block; overflow: visible; }
.grid { stroke: var(--grid); stroke-width: 1; }
.tick { fill: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.label { fill: var(--text-2); font-size: 13px; }
.value { fill: var(--text); font-size: 12px; font-weight: 600; }
.bar { fill: var(--series); }
.line { fill: none; stroke: var(--series); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.dot { fill: var(--series); stroke: var(--surface); stroke-width: 2; }
.hit { fill: transparent; }
.mark { outline: none; cursor: default; }
.mark:hover .bar, .mark:focus .bar { opacity: .8; }
.crosshair { stroke: var(--muted); stroke-width: 1; visibility: hidden; }
#tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 13px;
  box-shadow: 0 2px 8px rgba(0,0,0,.12); display: none; }
#tip strong { display: block; font-size: 15px; }
#tip span { color: var(--text-2); }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
pre { white-space: pre-wrap; word-break: break-word; font-size: 12px; margin: 0; }
.stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.stat .v { font-size: 20px; font-weight: 600; }
"""

_SCRIPT = """
const tip = document.getElementById('tip');
const cross = document.querySelector('.crosshair');
function show(el, x, y) {
  tip.replaceChildren();
  const v = document.createElement('strong'); v.textContent = el.dataset.value;
  const l = document.createElement('span'); l.textContent = el.dataset.label;
  tip.append(v, l); tip.style.display = 'block';
  tip.style.left = (x + 14) + 'px'; tip.style.top = (y + 14) + 'px';
  if (cross && el.dataset.x) { cross.setAttribute('x1', el.dataset.x); cross.setAttribute('x2', el.dataset.x);
    cross.style.visibility = 'visible'; }
}
function hide() { tip.style.display = 'none'; if (cross) cross.style.visibility = 'hidden'; }
document.querySelectorAll('.mark').forEach(el => {
  el.addEventListener('pointermove', e => show(el, e.clientX, e.clientY));
  el.addEventListener('pointerleave', hide);
  el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); show(el, r.left, r.top); });
  el.addEventListener('blur', hide);
});
"""


def render_html(question: str, answer: str, sql: str | None, columns: list[str],
                rows: list[dict[str, Any]], chart: ChartSpec,
                summary: list[ColumnSummary]) -> str:
    e = html.escape
    chart_html = ""
    if chart.type == "bar":
        chart_html = _bar_svg(chart)
    elif chart.type == "line":
        chart_html = _line_svg(chart)

    stats = "".join(
        f'<div class="card stat"><div class="meta">{e(s.name)} (total / mean)</div>'
        f'<div class="v">{_format_number(s.total)}</div>'
        f'<div class="meta">mean {_format_number(s.mean)} · min {_format_number(s.min)} · '
        f'max {_format_number(s.max)}</div></div>'
        for s in summary if s.kind == "number" and not _TIME_NAME.search(s.name)
        and not _ID_NAME.search(s.name)
    )

    def cell(column: str, value: Any) -> str:
        number = _as_number(value)
        if number is not None:
            return f'<td class="num">{e(_format_number(number))}</td>'
        return f"<td>{e('' if value is None else str(value))}</td>"

    header = "".join(f"<th>{e(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(cell(c, row.get(c)) for c in columns) + "</tr>" for row in rows)

    sections = [f"<h1>{e(question)}</h1>", f'<p class="answer">{e(answer)}</p>']
    if chart_html:
        sections.append(f'<h2>{e(chart.y_label)} by {e(chart.x_label)}</h2>'
                        f'<div class="card">{chart_html}</div>')
    if stats:
        sections.append(f'<h2>Summary</h2><div class="stats">{stats}</div>')
    sections.append(f'<h2>Data ({len(rows)} row{"s" if len(rows) != 1 else ""})</h2>'
                    f'<div class="card table-wrap"><table><thead><tr>{header}</tr></thead>'
                    f'<tbody>{body}</tbody></table></div>')
    if sql:
        sections.append(f'<h2>SQL</h2><div class="card"><pre>{e(sql.strip())}</pre></div>')
    sections.append('<p class="meta">Generated by DataPilot AI. Numbers come from the query '
                    'results above.</p>')

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>DataPilot Report</title><style>{_STYLE}</style></head>"
        f"<body><main>{''.join(sections)}</main><div id=\"tip\" role=\"status\"></div>"
        f"<script>{_SCRIPT}</script></body></html>"
    )


def rows_json_safe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(rows, default=str))
