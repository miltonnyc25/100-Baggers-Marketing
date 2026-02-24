#!/usr/bin/env python3
"""Capture real screenshots from 100baggers.club for marketing slides."""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).parent / "captures"
OUTPUT_DIR.mkdir(exist_ok=True)

BASE = "https://www.100baggers.club"
WAIT = "domcontentloaded"
TIMEOUT = 90000
SETTLE = 5000  # ms to wait after load for JS rendering


def goto(page, url):
    page.goto(url, wait_until=WAIT, timeout=TIMEOUT)
    page.wait_for_timeout(SETTLE)


def scroll_and_capture(page, name, positions):
    for i, y in enumerate(positions):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(1000)
        fname = f"{name}_scroll_{i:02d}.png"
        page.screenshot(path=str(OUTPUT_DIR / fname), full_page=False)
        print(f"   -> {fname} (y={y})")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            locale="zh-CN",
        )

        # ── 1. Reports listing page ──
        print("1. Capturing reports listing page...")
        page = ctx.new_page()
        goto(page, f"{BASE}/zh/reports")
        page.screenshot(path=str(OUTPUT_DIR / "reports_page_top.png"), full_page=False)
        print("   -> reports_page_top.png")
        scroll_and_capture(page, "reports", [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000])
        page.close()

        # ── 2. Tesla report (iframe content) ──
        print("\n2. Capturing Tesla report...")
        page = ctx.new_page()
        goto(page, f"{BASE}/reports/tsla/index.html")
        page.screenshot(path=str(OUTPUT_DIR / "tsla_top.png"), full_page=False)
        print("   -> tsla_top.png")
        scroll_and_capture(page, "tsla", [600, 1200, 1800, 2400, 3200, 4000, 5000, 6000, 8000, 10000, 13000, 16000, 20000, 25000, 30000])
        page.close()

        # ── 3. TSMC report ──
        print("\n3. Capturing TSMC report...")
        page = ctx.new_page()
        goto(page, f"{BASE}/reports/tsm/index.html")
        page.screenshot(path=str(OUTPUT_DIR / "tsm_top.png"), full_page=False)
        print("   -> tsm_top.png")
        scroll_and_capture(page, "tsm", [600, 1200, 1800, 2400, 3200, 4000, 5000, 6000, 8000, 10000, 13000, 16000, 20000, 25000, 30000])
        page.close()

        # ── 4. Google report ──
        print("\n4. Capturing Google report...")
        page = ctx.new_page()
        goto(page, f"{BASE}/reports/googl/index.html")
        page.screenshot(path=str(OUTPUT_DIR / "googl_top.png"), full_page=False)
        print("   -> googl_top.png")
        scroll_and_capture(page, "googl", [600, 1200, 1800, 2400, 3200, 4000, 5000, 6000, 8000, 10000, 13000, 16000, 20000, 25000, 30000])
        page.close()

        # ── 5. Homepage ──
        print("\n5. Capturing homepage...")
        page = ctx.new_page()
        goto(page, f"{BASE}/zh")
        page.screenshot(path=str(OUTPUT_DIR / "homepage_top.png"), full_page=False)
        print("   -> homepage_top.png")
        page.close()

        browser.close()

    print(f"\nDone! All captures saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
