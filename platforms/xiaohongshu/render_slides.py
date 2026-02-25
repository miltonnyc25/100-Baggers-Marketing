"""
Xiaohongshu slide image renderer.

Provides two rendering systems:

1. render_all_slides() — Legacy text-based renderer using templates/slide.html.
   Each slide is a text string that gets formatted into cover/content/CTA variants.

2. render_component_slides() — Component-based renderer using templates/slide_base.html.
   Each slide is a dict with an 'html' key containing pre-composed HTML using
   predefined CSS classes. The HTML is embedded into a shared base template.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "slide.html"
_BASE_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "slide_base.html"


# =====================================================================
# Legacy text-based rendering (slide.html)
# =====================================================================

def _build_cover_body(text: str) -> str:
    """Build inner HTML for the cover slide (slide 1)."""
    parts = text.split("\n", 1)
    hook = parts[0].strip()
    sub = parts[1].strip() if len(parts) > 1 else ""
    html = f'<div class="hook">{hook}</div>'
    if sub:
        html += f'\n    <div class="sub">{sub}</div>'
    return html


def _build_content_body(text: str, slide_num: int) -> str:
    """Build inner HTML for a content slide (slides 2 to N-1)."""
    num_str = f"{slide_num:02d}"
    return (
        f'<div class="slide-num">{num_str}</div>\n'
        f'    <div class="body-text">{text}</div>'
    )


def _build_cta_body(text: str, ticker: str) -> str:
    """Build inner HTML for the CTA slide (last slide)."""
    return (
        f'<div class="cta-text">{text}</div>\n'
        f'    <a class="cta-link" href="https://www.100baggers.club/reports/{ticker.lower()}">'
        f"100Baggers.Club</a>\n"
        f'    <div class="qr-hint">扫码查看完整深度报告</div>'
    )


def _fill_template(
    template: str,
    slide_text: str,
    slide_class: str,
    slide_body: str,
    ticker: str,
    company_name: str,
    slide_number: int,
    total_slides: int,
) -> str:
    """Fill the HTML template with slide-specific content."""
    html = template
    html = html.replace("{{SLIDE_CLASS}}", slide_class)
    html = html.replace("{{SLIDE_BODY}}", slide_body)
    html = html.replace("{{TICKER}}", ticker.upper())
    html = html.replace("{{COMPANY}}", company_name)
    html = html.replace("{{SLIDE_NUMBER}}", str(slide_number))
    html = html.replace("{{TOTAL_SLIDES}}", str(total_slides))
    return html


def html_to_jpg(html_path: Path, jpg_path: Path, width: int = 1080, height: int = 1440,
                quality: int = 90) -> Path:
    """Render a single HTML file to a JPG image using Playwright."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(jpg_path), type="jpeg", quality=quality)
        browser.close()

    log.info("Rendered %s -> %s", html_path.name, jpg_path.name)
    return jpg_path


def render_all_slides(
    slides: list[str],
    ticker: str,
    output_dir: Path,
    company_name: str = "",
    title: str = "",
) -> list[Path]:
    """
    Render slide text strings into numbered JPG files.

    Args:
        slides: List of slide text strings (5-8 items).
        ticker: Stock ticker symbol.
        output_dir: Directory to write slide_01.jpg, slide_02.jpg, etc.
        company_name: Company display name (for header).
        title: Optional title override for the cover slide.

    Returns:
        List of paths to the generated JPG files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    total = len(slides)
    jpg_paths: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="xhs-slides-") as tmp_dir:
        tmp = Path(tmp_dir)

        for i, text in enumerate(slides, 1):
            if i == 1:
                slide_class = "slide-cover"
                cover_text = title if title else text
                body = _build_cover_body(cover_text)
            elif i == total:
                slide_class = "slide-cta"
                body = _build_cta_body(text, ticker)
            else:
                slide_class = "slide-content"
                body = _build_content_body(text, i)

            html_content = _fill_template(
                template, text, slide_class, body,
                ticker, company_name, i, total,
            )

            html_path = tmp / f"slide_{i:02d}.html"
            html_path.write_text(html_content, encoding="utf-8")

            jpg_path = output_dir / f"slide_{i:02d}.jpg"
            html_to_jpg(html_path, jpg_path)
            jpg_paths.append(jpg_path)

    log.info("Rendered %d slides for %s to %s", total, ticker, output_dir)
    return jpg_paths


# =====================================================================
# Component-based rendering (slide_base.html)
# =====================================================================

_BASE_TEMPLATE_CACHE: str | None = None


def _load_base_template() -> str:
    """Load and cache the base template."""
    global _BASE_TEMPLATE_CACHE
    if _BASE_TEMPLATE_CACHE is None:
        _BASE_TEMPLATE_CACHE = _BASE_TEMPLATE_PATH.read_text(encoding="utf-8")
    return _BASE_TEMPLATE_CACHE


def render_component_slides(
    slides: list[dict],
    ticker: str,
    output_dir: Path,
    company_name: str = "",
) -> list[Path]:
    """
    Render component-based slide dicts into numbered PNG files.

    Each slide dict must have an 'html' key containing HTML content
    that uses the predefined CSS classes from slide_base.html.

    Uses a single Playwright browser instance for efficiency.
    Output is 2x scale (2160x2880) for crisp text.

    Args:
        slides: List of dicts, each with an 'html' key.
        ticker: Stock ticker symbol.
        output_dir: Directory to write slide_01.png, slide_02.png, etc.
        company_name: Company display name (for header).

    Returns:
        List of paths to the generated PNG files.
    """
    from playwright.sync_api import sync_playwright

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_template = _load_base_template()
    total = len(slides)
    png_paths: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="xhs-component-") as tmp_dir:
        tmp = Path(tmp_dir)

        # Pre-generate all HTML files
        html_files: list[Path] = []
        for i, slide in enumerate(slides, 1):
            html_content = base_template
            html_content = html_content.replace("{{CONTENT}}", slide["html"])
            html_content = html_content.replace("{{TICKER}}", ticker.upper())
            html_content = html_content.replace("{{COMPANY}}", company_name)
            html_content = html_content.replace("{{SLIDE_NUMBER}}", str(i))
            html_content = html_content.replace("{{TOTAL_SLIDES}}", str(total))
            html_content = html_content.replace("{{TICKER_LOWER}}", ticker.lower())

            html_path = tmp / f"slide_{i:02d}.html"
            html_path.write_text(html_content, encoding="utf-8")
            html_files.append(html_path)

        # Single browser instance for all slides
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1080, "height": 1440},
                device_scale_factor=2,
            )

            for i, html_path in enumerate(html_files, 1):
                page.goto(f"file://{html_path}")
                page.wait_for_load_state("networkidle")

                png_path = output_dir / f"slide_{i:02d}.png"
                page.screenshot(path=str(png_path), type="png")
                png_paths.append(png_path)
                log.info("Rendered slide_%02d.png", i)

            browser.close()

    log.info("Rendered %d component slides for %s to %s", total, ticker, output_dir)
    return png_paths
