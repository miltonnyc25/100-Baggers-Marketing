"""
Xiaohongshu slide image renderer.

Renders slide text strings into 1080x1440 JPG images using
Playwright and the HTML template at templates/slide.html.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "slide.html"


def _build_cover_body(text: str) -> str:
    """Build inner HTML for the cover slide (slide 1)."""
    # Split on first period/newline to get hook vs sub
    parts = text.split("\n", 1)
    hook = parts[0].strip()
    sub = parts[1].strip() if len(parts) > 1 else ""
    html = f'<div class="hook">{hook}</div>'
    if sub:
        html += f'\n    <div class="sub">{sub}</div>'
    return html


def _build_content_body(text: str, slide_num: int) -> str:
    """Build inner HTML for a content slide (slides 2 to N-1)."""
    # Format the slide number as a large background number
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

    # Use a single temp dir for all intermediate HTML files
    with tempfile.TemporaryDirectory(prefix="xhs-slides-") as tmp_dir:
        tmp = Path(tmp_dir)

        for i, text in enumerate(slides, 1):
            # Determine slide variant
            if i == 1:
                slide_class = "slide-cover"
                # Use title as cover hook if provided, otherwise use slide text
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
