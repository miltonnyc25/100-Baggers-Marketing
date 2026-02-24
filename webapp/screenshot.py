"""
Capture screenshots of ECharts charts and data tables from rendered reports.

Uses Playwright to render the report HTML and take element-level JPG
screenshots. Supports language-aware URLs (Chinese vs English reports).

Explicitly excludes Mermaid diagrams — only real data visualizations.
"""

from __future__ import annotations

import asyncio
import http.server
import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_INVESTVIEW_PUBLIC = Path(os.path.expanduser(
    "~/Downloads/InvestView_v0/public"
))
_SCREENSHOT_DIR = Path(__file__).resolve().parent / "static" / "screenshots"

# Theme → keywords for matching <h2> headings to segments
_THEME_KEYWORDS: dict[str, list[str]] = {
    "executive_overview": ["executive summary", "核心结论", "核心矛盾", "overview", "summary", "概述"],
    "financial_deep_dive": ["financial", "财务", "revenue", "收入", "margin", "dcf", "valuation", "估值", "earnings", "现金流"],
    "competitive_position": ["competitive", "竞争", "moat", "护城河", "market share", "行业", "industry"],
    "growth_technology": ["growth", "增长", "technology", "技术", "ai", "product", "产品", "innovation"],
    "risk_verdict": ["risk", "风险", "scenario", "bear case", "bull case", "challenge"],
}

# Minimum rows for a table to be worth screenshotting
_MIN_TABLE_ROWS = 3

# Regex for numeric-heavy content (tables with real data)
_NUMERIC_RE = re.compile(r'[\$%\d]')


def _start_http_server(root: Path, port: int = 8765) -> http.server.HTTPServer:
    """Start a simple HTTP server on a background thread."""

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format, *args):
            pass  # suppress HTTP logs

    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def _is_data_rich_table(table_el) -> bool:
    """Check if a table element has enough rows and numeric data."""
    rows = await table_el.query_selector_all("tr")
    if len(rows) < _MIN_TABLE_ROWS:
        return False
    text = await table_el.inner_text()
    numeric_chars = len(_NUMERIC_RE.findall(text))
    total_chars = len(text)
    if total_chars == 0:
        return False
    # At least 10% numeric/currency characters
    return (numeric_chars / total_chars) > 0.10


async def capture_report_screenshots(
    ticker: str,
    segment_theme: str,
    session_id: str,
    segment_id: str = "seg1",
    max_screenshots: int = 3,
    language: str = "zh",
) -> list[str]:
    """
    Capture ECharts chart and data table screenshots from a rendered report.

    Args:
        ticker: Stock ticker (e.g. "orcl")
        segment_theme: Theme key (e.g. "financial_deep_dive")
        session_id: Session ID for organizing screenshots
        segment_id: Segment ID (e.g. "seg1")
        max_screenshots: Maximum number of screenshots to capture
        language: "zh" for Chinese report, "en" for English report

    Returns:
        List of relative URLs like "/screenshots/{session_id}/{segment_id}/chart_0.jpg"
    """
    ticker = ticker.lower()

    # Language-aware report path
    if language == "en":
        report_path = _INVESTVIEW_PUBLIC / "reports" / ticker / "en" / "index.html"
    else:
        report_path = _INVESTVIEW_PUBLIC / "reports" / ticker / "index.html"

    if not report_path.exists():
        # Fallback: try the other language
        fallback = _INVESTVIEW_PUBLIC / "reports" / ticker / "index.html"
        if language == "en" and fallback.exists():
            report_path = fallback
            log.info("English report not found for %s, falling back to Chinese", ticker)
        else:
            log.warning("Report HTML not found: %s", report_path)
            return []

    # Build URL path relative to public root
    rel_path = report_path.relative_to(_INVESTVIEW_PUBLIC)
    url_path = str(rel_path).replace(os.sep, "/")

    # Prepare output directory
    out_dir = _SCREENSHOT_DIR / session_id / segment_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Start HTTP server
    port = 8765
    server: Optional[http.server.HTTPServer] = None
    try:
        server = _start_http_server(_INVESTVIEW_PUBLIC, port)
    except OSError:
        port = 8766
        try:
            server = _start_http_server(_INVESTVIEW_PUBLIC, port)
        except OSError:
            log.warning("Could not start HTTP server on port %d or %d", 8765, 8766)
            return []

    url = f"http://127.0.0.1:{port}/{url_path}?demo=true"

    screenshots: list[str] = []
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(url, wait_until="networkidle")

            # Wait for ECharts to render
            await page.wait_for_timeout(6000)

            # Dismiss the "恭喜解锁完整报告" invite overlay that blocks content
            await page.evaluate("""() => {
                // Primary: call the page's own close function
                if (typeof closeInviteGuide === 'function') {
                    closeInviteGuide();
                }
                // Fallback: force-hide the overlay element
                const overlay = document.getElementById('invite-guide-overlay');
                if (overlay) {
                    overlay.style.display = 'none';
                    overlay.classList.remove('visible');
                }
            }""")
            await page.wait_for_timeout(500)

            # Get theme keywords
            keywords = _THEME_KEYWORDS.get(segment_theme, [])

            # Find <h2> headings that match segment theme keywords
            h2_elements = await page.query_selector_all("h2")
            matched_sections: list = []
            for h2 in h2_elements:
                text = (await h2.inner_text()).lower()
                if any(kw in text for kw in keywords):
                    matched_sections.append(h2)

            # If no heading matches, scan the whole page
            if not matched_sections:
                matched_sections = [None]

            count = 0
            for section in matched_sections:
                if count >= max_screenshots:
                    break

                # --- Priority 1: ECharts containers ---
                chart_selectors = [
                    "[id^='chart-']",  # ECharts div containers
                    "canvas",          # Rendered ECharts canvases
                ]

                for selector in chart_selectors:
                    if count >= max_screenshots:
                        break

                    elements = await page.query_selector_all(selector)
                    for el in elements:
                        if count >= max_screenshots:
                            break

                        el_box = await el.bounding_box()
                        if not el_box or el_box["width"] < 200 or el_box["height"] < 100:
                            continue

                        # If we have a matched section, only take elements near it
                        if section is not None:
                            section_box = await section.bounding_box()
                            if not section_box:
                                continue
                            if el_box["y"] < section_box["y"]:
                                continue
                            if el_box["y"] - section_box["y"] > 1500:
                                continue

                        filename = f"chart_{count}.jpg"
                        filepath = out_dir / filename
                        try:
                            await el.screenshot(
                                path=str(filepath), type="jpeg", quality=90,
                            )
                            rel_url = f"/screenshots/{session_id}/{segment_id}/{filename}"
                            screenshots.append(rel_url)
                            count += 1
                            log.info("Captured ECharts screenshot: %s", rel_url)
                        except Exception as e:
                            log.warning("Screenshot failed for chart element: %s", e)

                # --- Priority 2: Data-rich tables (only if few charts found) ---
                if count < max_screenshots:
                    tables = await page.query_selector_all("table")
                    for table in tables:
                        if count >= max_screenshots:
                            break

                        tbl_box = await table.bounding_box()
                        if not tbl_box or tbl_box["width"] < 200 or tbl_box["height"] < 60:
                            continue

                        # If we have a matched section, only take tables near it
                        if section is not None:
                            section_box = await section.bounding_box()
                            if not section_box:
                                continue
                            if tbl_box["y"] < section_box["y"]:
                                continue
                            if tbl_box["y"] - section_box["y"] > 1500:
                                continue

                        # Only capture data-rich tables
                        if not await _is_data_rich_table(table):
                            continue

                        filename = f"chart_{count}.jpg"
                        filepath = out_dir / filename
                        try:
                            await table.screenshot(
                                path=str(filepath), type="jpeg", quality=90,
                            )
                            rel_url = f"/screenshots/{session_id}/{segment_id}/{filename}"
                            screenshots.append(rel_url)
                            count += 1
                            log.info("Captured table screenshot: %s", rel_url)
                        except Exception as e:
                            log.warning("Screenshot failed for table element: %s", e)

            await browser.close()

    except ImportError:
        log.error("playwright not installed. Run: pip install playwright && playwright install chromium")
    except Exception:
        log.exception("Screenshot capture failed")
    finally:
        if server:
            server.shutdown()

    return screenshots


def capture_report_screenshots_sync(
    ticker: str,
    segment_theme: str,
    session_id: str,
    segment_id: str = "seg1",
    max_screenshots: int = 3,
    language: str = "zh",
) -> list[str]:
    """Synchronous wrapper for capture_report_screenshots."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                capture_report_screenshots(
                    ticker, segment_theme, session_id, segment_id,
                    max_screenshots, language,
                )
            ).result()
    else:
        return asyncio.run(
            capture_report_screenshots(
                ticker, segment_theme, session_id, segment_id,
                max_screenshots, language,
            )
        )
