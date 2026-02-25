"""
Chart catalog builder — parses HTML reports for ECharts containers.

Scans index.html for <div id="chart-xxx"> containers and extracts
chart metadata (ID, title, chapter location) for the strategist prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engine.config import find_html_report


@dataclass
class ChartEntry:
    chart_id: str           # "chart-margin-trend"
    chart_index: int        # 1-based sequential number
    chapter_heading: str    # "第2章：财务全景"
    chart_title: str        # extracted from ECharts title.text config
    chart_type: str = ""    # "折线图", "柱状图", "雷达图", "饼图", etc.


def build_chart_catalog(ticker: str) -> list[ChartEntry]:
    """Parse the HTML report for a ticker and return all chart entries.

    Each entry maps a chart div ID to its chapter heading and ECharts title.
    Returns empty list if no HTML report found.
    """
    html_path = find_html_report(ticker)
    if not html_path or not html_path.exists():
        return []

    html = html_path.read_text(encoding="utf-8")
    return _parse_charts_from_html(html)


def _parse_charts_from_html(html: str) -> list[ChartEntry]:
    """Extract chart entries from raw HTML content."""
    entries: list[ChartEntry] = []

    # Build a mapping of line positions to h1 headings.
    # We track the "current chapter" as we scan the HTML top-to-bottom.
    lines = html.split("\n")

    # Pre-scan: find all h1 headings with their line numbers
    h1_positions: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = re.search(r"<h1[^>]*>(.*?)</h1>", line)
        if m:
            heading_text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if heading_text:
                h1_positions.append((i, heading_text))

    # Pre-scan: find all chart divs with their line numbers
    chart_positions: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = re.search(r'id="(chart-[^"]+)"', line)
        if m:
            chart_positions.append((i, m.group(1)))

    # Extract chart titles and types from nearby script blocks.
    # The title is in the ECharts option: title: { text: '...' }
    chart_titles: dict[str, str] = {}
    chart_types: dict[str, str] = {}
    for chart_line, chart_id in chart_positions:
        # Look in the next 80 lines for the title and type config
        search_block = "\n".join(lines[chart_line:chart_line + 80])
        title = _extract_echart_title(search_block)
        chart_titles[chart_id] = title
        chart_type = _detect_echart_type(search_block)
        chart_types[chart_id] = chart_type

    # Match each chart to its chapter (last h1 before the chart's line)
    chart_index = 0
    for chart_line, chart_id in chart_positions:
        chart_index += 1
        chapter = ""
        for h1_line, h1_text in h1_positions:
            if h1_line < chart_line:
                chapter = h1_text
            else:
                break

        entries.append(ChartEntry(
            chart_id=chart_id,
            chart_index=chart_index,
            chapter_heading=chapter,
            chart_title=chart_titles.get(chart_id, ""),
            chart_type=chart_types.get(chart_id, ""),
        ))

    return entries


def _extract_echart_title(script_block: str) -> str:
    """Extract the title.text value from an ECharts option block.

    Handles patterns like:
      title: { text: 'ANET六年利润率趋势 (FY2020-FY2025)', ...}
      title: { text: "估值方法光谱 (低→高)", ...}
    Also handles unicode escapes like \\u4e94\\u5f15\\u64ce.
    """
    # Pattern: title: { text: 'xxx' } or title: { text: "xxx" }
    m = re.search(
        r"""title:\s*\{\s*text:\s*(['"])(.*?)\1""",
        script_block,
        re.DOTALL,
    )
    if not m:
        return ""

    raw_title = m.group(2)

    # Decode unicode escapes (e.g. \u4e94 → 五) — only if they exist
    if "\\u" in raw_title:
        try:
            raw_title = raw_title.encode("raw_unicode_escape").decode("unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass  # Keep as-is if decode fails

    # Clean up newline escapes
    raw_title = raw_title.replace("\\n", " ").strip()
    return raw_title


def _detect_echart_type(script_block: str) -> str:
    """Detect chart type from ECharts option block.

    Returns a Chinese label: 折线图, 柱状图, 雷达图, 饼图, 散点图, etc.
    """
    # Radar charts have a `radar:` config instead of xAxis/yAxis
    if re.search(r"\bradar\s*:", script_block):
        return "雷达图"

    # Collect all series type declarations
    types_found = re.findall(r"type\s*:\s*['\"](\w+)['\"]", script_block)
    # Filter to known ECharts series types
    echart_types = {"bar", "line", "pie", "scatter", "radar", "heatmap",
                    "treemap", "sunburst", "funnel", "gauge", "waterfall"}
    series_types = [t for t in types_found if t in echart_types]

    if not series_types:
        return ""

    type_map = {
        "line": "折线图",
        "bar": "柱状图",
        "pie": "饼图",
        "scatter": "散点图",
        "radar": "雷达图",
        "heatmap": "热力图",
        "treemap": "树图",
        "sunburst": "旭日图",
        "funnel": "漏斗图",
        "gauge": "仪表盘",
        "waterfall": "瀑布图",
    }

    # If mixed types (e.g. bar+line combo), note the primary
    primary = series_types[0]
    if len(set(series_types)) > 1:
        unique = list(dict.fromkeys(series_types))  # preserve order, dedupe
        labels = [type_map.get(t, t) for t in unique[:2]]
        return "+".join(labels)

    return type_map.get(primary, primary)


def format_catalog_for_prompt(catalog: list[ChartEntry]) -> str:
    """Format the chart catalog as a readable list for the strategist prompt.

    Example output:
      图1: chart-margin-trend [第2章：财务全景] (折线图) — ANET六年利润率趋势 (FY2020-FY2025)
      图2: chart-five-engine-radar [第17章：五引擎模型] (雷达图) — 五维评分雷达
    """
    if not catalog:
        return "(No charts found in HTML report)"

    lines = []
    for entry in catalog:
        chapter_tag = f"[{entry.chapter_heading}]" if entry.chapter_heading else "[未知章节]"
        type_tag = f" ({entry.chart_type})" if entry.chart_type else ""
        title_part = f" — {entry.chart_title}" if entry.chart_title else ""
        lines.append(
            f"图{entry.chart_index}: {entry.chart_id} {chapter_tag}{type_tag}{title_part}"
        )
    return "\n".join(lines)


# ── CLI test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "anet"
    catalog = build_chart_catalog(ticker)
    print(f"{len(catalog)} charts found for {ticker.upper()}:\n")
    print(format_catalog_for_prompt(catalog))
