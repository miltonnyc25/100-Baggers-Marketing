"""
Chart screenshot capture — renders HTML reports and captures specific charts.

Uses Playwright to render the report HTML, waits for ECharts to init,
then captures specific chart divs by ID as JPG files.

Built on the same patterns as webapp/screenshot.py.
"""

from __future__ import annotations

import asyncio
import http.server
import os
import threading
from pathlib import Path
from typing import Optional

_INVESTVIEW_PUBLIC = Path(os.path.expanduser(
    "~/Downloads/InvestView_v0/public"
))


def _start_http_server(root: Path, port: int) -> http.server.HTTPServer:
    """Start a simple HTTP server on a background daemon thread."""

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format, *args):
            pass  # suppress HTTP logs

    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def _capture_charts_async(
    ticker: str, chart_ids: list[str], output_dir: Path
) -> dict[str, Path]:
    """Async implementation: render report HTML and capture chart divs."""
    ticker = ticker.lower()
    report_path = _INVESTVIEW_PUBLIC / "reports" / ticker / "index.html"

    if not report_path.exists():
        print(f"[chart_screenshot] Report HTML not found: {report_path}")
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)

    # Build URL relative to public root
    rel_path = report_path.relative_to(_INVESTVIEW_PUBLIC)
    url_path = str(rel_path).replace(os.sep, "/")

    # Start HTTP server
    server: Optional[http.server.HTTPServer] = None
    port = 8767
    for p in (8767, 8768, 8769):
        try:
            server = _start_http_server(_INVESTVIEW_PUBLIC, p)
            port = p
            break
        except OSError:
            continue

    if server is None:
        print("[chart_screenshot] Could not start HTTP server")
        return {}

    results: dict[str, Path] = {}
    url = f"http://127.0.0.1:{port}/{url_path}?demo=true"

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(url, wait_until="networkidle")

            # Wait for ECharts to render
            await page.wait_for_timeout(6000)

            # Dismiss the invite overlay that blocks content
            await page.evaluate("""() => {
                if (typeof closeInviteGuide === 'function') {
                    closeInviteGuide();
                }
                const overlay = document.getElementById('invite-guide-overlay');
                if (overlay) {
                    overlay.style.display = 'none';
                    overlay.classList.remove('visible');
                }
            }""")
            await page.wait_for_timeout(500)

            # Capture each requested chart
            for chart_id in chart_ids:
                el = await page.query_selector(f"#{chart_id}")
                if not el:
                    print(f"[chart_screenshot] Chart element not found: #{chart_id}")
                    continue

                el_box = await el.bounding_box()
                if not el_box or el_box["width"] < 100 or el_box["height"] < 50:
                    print(f"[chart_screenshot] Chart too small or invisible: #{chart_id}")
                    continue

                filename = f"{chart_id}.jpg"
                filepath = output_dir / filename
                try:
                    await el.screenshot(
                        path=str(filepath), type="jpeg", quality=90,
                    )
                    results[chart_id] = filepath
                    print(f"[chart_screenshot] Captured: {filepath.name}")
                except Exception as e:
                    print(f"[chart_screenshot] Failed to capture {chart_id}: {e}")

            await browser.close()

    except ImportError:
        print("[chart_screenshot] playwright not installed. "
              "Run: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"[chart_screenshot] Capture failed: {e}")
    finally:
        if server:
            server.shutdown()

    return results


def capture_chart_by_ids(
    ticker: str, chart_ids: list[str], output_dir: Path
) -> dict[str, Path]:
    """Render HTML report and capture specific chart divs as JPG.

    Args:
        ticker: Stock ticker (e.g. "anet")
        chart_ids: List of chart div IDs (e.g. ["chart-margin-trend"])
        output_dir: Directory to save screenshots

    Returns:
        Mapping of {chart_id: screenshot_path} for successfully captured charts.
    """
    if not chart_ids:
        return {}

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                _capture_charts_async(ticker, chart_ids, output_dir),
            ).result()
    else:
        return asyncio.run(
            _capture_charts_async(ticker, chart_ids, output_dir),
        )


# ── CLI test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "anet"
    ids = sys.argv[2:] if len(sys.argv) > 2 else ["chart-margin-trend"]
    out = Path("/tmp/chart-screenshots")
    result = capture_chart_by_ids(ticker, ids, out)
    for cid, path in result.items():
        print(f"  {cid} → {path}")
