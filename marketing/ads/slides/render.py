#!/usr/bin/env python3
"""Render slide HTML files to PNG images using Playwright."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

SLIDES_DIR = Path(__file__).parent
OUTPUT_DIR = SLIDES_DIR / "images"
OUTPUT_DIR.mkdir(exist_ok=True)

WIDTH = 1080
HEIGHT = 1440

def main():
    html_files = sorted(SLIDES_DIR.glob("slide*.html"))
    if not html_files:
        print("No slide HTML files found.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for html_file in html_files:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.goto(f"file://{html_file.resolve()}")
            page.wait_for_timeout(500)

            out_path = OUTPUT_DIR / f"{html_file.stem}.png"
            page.screenshot(path=str(out_path), full_page=False)
            print(f"  {html_file.name} -> {out_path.name}")
            page.close()

        browser.close()

    print(f"\nDone! {len(html_files)} slides rendered to {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
