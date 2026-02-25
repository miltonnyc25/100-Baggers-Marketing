#!/usr/bin/env python3
"""
Deep research report cover generator.

Generates 3:4 ratio (1080x1440) covers for 100Baggers deep research reports.
Design: deep navy background + warm amber/gold accent.
Layout: large company name (line 1) + "深度研究报告" (line 2).

Usage:
    python webapp/generate_cover.py TSLA                    # Single ticker
    python webapp/generate_cover.py TSLA AAPL META          # Multiple tickers
    python webapp/generate_cover.py --all                   # All tickers
"""

import os
import sys
from pathlib import Path

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.config import AVAILABLE_TICKERS

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "cover_report.html"
_OUTPUT_DIR = Path(__file__).resolve().parent / "static" / "covers"

# ── Cover title mapping ──────────────────────────────────────────────
# Main title: the most recognizable name for each company.
COVER_TITLES = {
    "AAPL": "APPLE",
    "AMAT": "AMAT",
    "AMD": "AMD",
    "AMZN": "AMAZON",
    "ANET": "ARISTA",
    "APP": "APPLOVIN",
    "ASML": "ASML",
    "COST": "COSTCO",
    "ETN": "EATON",
    "GOOGL": "GOOGLE",
    "KLAC": "KLA",
    "LRCX": "LAM",
    "META": "META",
    "MSFT": "MICROSOFT",
    "MU": "MICRON",
    "ORCL": "ORACLE",
    "PG": "P&G",
    "PLTR": "PALANTIR",
    "RBLX": "ROBLOX",
    "RDDT": "REDDIT",
    "SMCI": "SMCI",
    "SOFI": "SOFI",
    "TSLA": "TESLA",
    "TSM": "TSMC",
    "VRT": "VERTIV",
}


def get_cover_title(ticker: str) -> str:
    """Get the cover main title for a ticker."""
    return COVER_TITLES.get(ticker.upper(), ticker.upper())


def _calc_font_size(name: str) -> int:
    """Calculate font size for the main title based on character count.

    Since we now control exact titles, optimize per length.
    """
    length = len(name)
    if length <= 3:
        return 250
    if length <= 4:
        return 220
    if length <= 5:
        return 200
    if length <= 6:
        return 170
    if length <= 8:
        return 150
    return 130


def generate_cover_html(ticker: str, title: str) -> str:
    """Generate HTML string for a cover image."""
    html = _TEMPLATE_PATH.read_text(encoding="utf-8")
    font_size = _calc_font_size(title)
    # "深度研究报告" = 6 Chinese chars; max that fits 1010px ≈ 160px
    label_font_size = min(font_size, 160)
    html = html.replace("{{TICKER}}", ticker.upper())
    html = html.replace("{{COMPANY_NAME}}", title.upper())
    html = html.replace("{{FONT_SIZE}}", str(font_size))
    html = html.replace("{{LABEL_FONT_SIZE}}", str(label_font_size))
    return html


def render_cover(ticker: str, title: str, output_dir: Path | None = None) -> Path:
    """Generate and render a cover image for a ticker.

    Returns the path to the generated JPEG file.
    """
    from playwright.sync_api import sync_playwright

    output_dir = output_dir or _OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    html = generate_cover_html(ticker, title)

    html_path = output_dir / f"{ticker.lower()}_cover.html"
    html_path.write_text(html, encoding="utf-8")

    image_path = output_dir / f"{ticker.lower()}_cover.jpg"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1440})
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(image_path), type="jpeg", quality=95)
        browser.close()

    html_path.unlink(missing_ok=True)

    size_kb = image_path.stat().st_size / 1024
    print(f"  {ticker.upper():5s} ({title:10s}) → {image_path.name} ({size_kb:.0f}KB)")
    return image_path


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    if "--all" in args:
        tickers = AVAILABLE_TICKERS
    else:
        tickers = [t.lower() for t in args if not t.startswith("-")]

    print(f"Generating covers for {len(tickers)} tickers...")
    for t in tickers:
        title = get_cover_title(t)
        render_cover(t, title)
    print("Done.")
