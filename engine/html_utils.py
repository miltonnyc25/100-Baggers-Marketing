"""
Shared HTML utilities for content publishing.

Functions:
- save_html: Save plain text as styled HTML with copy-to-clipboard command
- copy_to_clipboard: Copy HTML to macOS clipboard as rich text
- strip_html_to_text: Convert HTML post back to plain text
"""

from __future__ import annotations

import re
import html as html_lib
from pathlib import Path


def save_html(text_content: str, html_path: Path, chart_footer: str = "") -> None:
    """Save post as HTML file with a copy-to-clipboard command at the top.

    Converts plain text paragraphs into <p> tags with <br> for single newlines.
    Optionally appends a chart recommendation footer section.
    """
    # Normalize line endings
    text = text_content.replace("\r\n", "\n")

    # Strip the "--- 配图建议 ---" footer from post body (shown separately)
    if "\n--- 配图建议 ---" in text:
        text = text.split("\n--- 配图建议 ---")[0].rstrip()

    # Split into paragraphs on double newlines
    paragraphs = text.split("\n\n")

    html_parts = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # Escape HTML
        p = p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Preserve single newlines within a paragraph as <br>
        p = p.replace("\n", "<br>\n")
        html_parts.append(f"<p>{p}</p>")

    body = "\n".join(html_parts)

    # Chart footer section
    chart_html = ""
    if chart_footer:
        escaped = chart_footer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped = escaped.replace("\n", "<br>\n")
        chart_html = f'\n<div class="chart-footer"><p>{escaped}</p></div>'

    # Copy command
    copy_cmd = f"cat {html_path} | textutil -stdin -format html -convert rtf -stdout | pbcopy"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 720px; margin: 40px auto; line-height: 1.8; color: #333; }}
p {{ margin: 0.8em 0; }}
.copy-cmd {{ background: #f5f5f5; border: 1px solid #ddd; border-radius: 6px; padding: 12px 16px;
  margin-bottom: 30px; font-family: monospace; font-size: 12px; color: #666; word-break: break-all; }}
.copy-cmd strong {{ color: #333; font-size: 13px; }}
hr {{ border: none; border-top: 1px solid #eee; margin: 30px 0; }}
.chart-footer {{ background: #fffbe6; border: 1px solid #ffe58f; border-radius: 6px; padding: 12px 16px;
  margin-top: 20px; font-size: 13px; color: #8c8c00; }}
</style></head>
<body>
<div class="copy-cmd">
<strong>Copy to clipboard:</strong><br>
<code>{copy_cmd}</code>
</div>
<hr>
{body}
{chart_html}
</body></html>
"""
    html_path.write_text(html, encoding="utf-8")


def copy_to_clipboard(html_path: Path) -> bool:
    """Copy HTML content to macOS clipboard as rich text using textutil + pbcopy.

    Returns True on success. Only works on macOS.
    """
    import subprocess
    try:
        p1 = subprocess.Popen(
            ["textutil", "-stdin", "-format", "html", "-convert", "rtf", "-stdout"],
            stdin=open(html_path, "rb"),
            stdout=subprocess.PIPE,
        )
        p2 = subprocess.Popen(["pbcopy"], stdin=p1.stdout)
        p1.stdout.close()
        p2.communicate()
        return p2.returncode == 0
    except FileNotFoundError:
        print("[html_utils] textutil/pbcopy not found (macOS only)")
        return False


def strip_html_to_text(html_path: Path) -> str:
    """Convert an HTML post file back to plain text.

    Removes the copy-command div, chart-footer div, strips all HTML tags,
    decodes HTML entities, and normalizes whitespace.
    """
    raw = html_path.read_text(encoding="utf-8")

    # Remove the copy-cmd div
    raw = re.sub(r'<div class="copy-cmd">.*?</div>', "", raw, flags=re.DOTALL)

    # Remove the chart-footer div
    raw = re.sub(r'<div class="chart-footer">.*?</div>', "", raw, flags=re.DOTALL)

    # Remove <style> block
    raw = re.sub(r"<style>.*?</style>", "", raw, flags=re.DOTALL)

    # Remove <hr> tags
    raw = re.sub(r"<hr\s*/?>", "", raw)

    # Convert <br> to newlines
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)

    # Convert </p> to double newline (paragraph break)
    raw = re.sub(r"</p>", "\n\n", raw, flags=re.IGNORECASE)

    # Strip all remaining HTML tags
    raw = re.sub(r"<[^>]+>", "", raw)

    # Decode HTML entities
    raw = html_lib.unescape(raw)

    # Normalize whitespace: collapse 3+ newlines to 2, strip leading/trailing
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    raw = raw.strip()

    return raw
