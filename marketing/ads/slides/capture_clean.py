#!/usr/bin/env python3
"""Capture clean content-only screenshots: hide sidebar + header."""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT = Path(__file__).parent / "clean"
OUTPUT.mkdir(exist_ok=True)
BASE = "https://www.100baggers.club"
SETTLE = 6000

HIDE_CHROME = """
() => {
    // Hide the top navbar
    document.querySelectorAll('header, nav, [class*="navbar"], [class*="header"]').forEach(
        el => el.style.display = 'none'
    );
    // Hide sidebar
    document.querySelectorAll('[class*="sidebar"], [class*="Sidebar"], [class*="nav-panel"]').forEach(
        el => el.style.display = 'none'
    );
    // Hide the floating buttons (feedback, scroll-to-top)
    document.querySelectorAll('[class*="feedback"], [class*="Feedback"], button[class*="scroll"]').forEach(
        el => el.style.display = 'none'
    );
    // Remove fixed top bar from report pages
    const topBar = document.querySelector('.fixed, [style*="position: fixed"]');
    if (topBar) topBar.style.display = 'none';
}
"""

HIDE_REPORT_CHROME = """
() => {
    // Report pages have a specific layout
    // Hide sidebar toggle and sidebar
    const sidebar = document.querySelector('[class*="sidebar"], [class*="Sidebar"], aside, .toc-sidebar, #sidebar');
    if (sidebar) sidebar.style.display = 'none';

    // Hide the top blue header bar
    const headers = document.querySelectorAll('[class*="topbar"], [class*="TopBar"], [class*="header"], header');
    headers.forEach(el => { el.style.display = 'none'; });

    // Hide floating elements
    document.querySelectorAll('[class*="float"], [class*="Float"], [class*="back-to-top"], [class*="toolbar"]').forEach(
        el => el.style.display = 'none';
    );

    // Expand content to full width
    const main = document.querySelector('main, .main-content, [class*="content"], article');
    if (main) {
        main.style.marginLeft = '0';
        main.style.maxWidth = '100%';
        main.style.width = '100%';
    }
}
"""


def goto(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(SETTLE)


def capture_report_sections(page, name, scroll_positions):
    """Scroll through a report page and capture content-only screenshots."""
    # Try to collapse sidebar by clicking the toggle
    try:
        toggle = page.locator('button:has-text("‹"), button:has-text("«"), [class*="collapse"], [class*="toggle-sidebar"]').first
        if toggle.is_visible():
            toggle.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    # Inject CSS to hide chrome elements
    page.evaluate("""() => {
        const style = document.createElement('style');
        style.textContent = `
            header, nav, [class*="topbar"], [class*="TopBar"],
            [class*="toolbar"], [class*="Toolbar"],
            [class*="back-to-top"], [class*="BackToTop"],
            [class*="feedback"], [class*="Feedback"],
            .fixed-top, [style*="position: fixed"],
            [class*="sidebar-toggle"] { display: none !important; }
        `;
        document.head.appendChild(style);
    }""")
    page.wait_for_timeout(500)

    for i, y in enumerate(scroll_positions):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(800)
        fname = f"{name}_{i:02d}.png"
        page.screenshot(path=str(OUTPUT / fname), full_page=False)
        print(f"   -> {fname} (y={y})")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1200, "height": 900},
            device_scale_factor=2,
            locale="zh-CN",
        )

        # ── 1. Reports page (ecosystem map) ──
        print("1. Reports page...")
        page = ctx.new_page()
        goto(page, f"{BASE}/zh/reports")
        # Hide feedback button
        page.evaluate("""() => {
            document.querySelectorAll('[class*="feedback"], [class*="Feedback"]').forEach(
                el => el.style.display = 'none'
            );
        }""")
        page.wait_for_timeout(300)

        # Scroll to show the ecosystem map fully
        page.evaluate("window.scrollTo(0, 300)")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT / "ecosystem_map.png"), full_page=False)
        print("   -> ecosystem_map.png")

        # Report cards
        page.evaluate("window.scrollTo(0, 950)")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT / "report_cards.png"), full_page=False)
        print("   -> report_cards.png")
        page.close()

        # ── 2. Tesla report ──
        print("\n2. Tesla report...")
        page = ctx.new_page()
        goto(page, f"{BASE}/reports/tsla/index.html")
        capture_report_sections(page, "tsla", [
            2200,   # executive summary + key findings
            3000,   # financial table start
            3600,   # financial table + key discoveries
            4200,   # more key discoveries
            4800,   # profitability flowchart
            5400,   # quarterly breakdown
        ])
        page.close()

        # ── 3. TSMC report ──
        print("\n3. TSMC report...")
        page = ctx.new_page()
        goto(page, f"{BASE}/reports/tsm/index.html")
        capture_report_sections(page, "tsm", [
            2000,   # CQ questions
            3000,   # attention ranking table
            4000,   # executive summary
            5000,   # company portrait
            6000,   # revenue structure
            7000,   # revenue tables
        ])
        page.close()

        # ── 4. Google report ──
        print("\n4. Google report...")
        page = ctx.new_page()
        goto(page, f"{BASE}/reports/googl/index.html")
        capture_report_sections(page, "googl", [
            1500,   # executive summary table
            2000,   # key signals
            3000,   # company portrait
            4000,   # org chart / business overview
            5000,   # six business segments
            6000,   # more analysis
        ])
        page.close()

        browser.close()

    print(f"\nDone! Clean captures in {OUTPUT}/")


if __name__ == "__main__":
    main()
