#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xueqiu (雪球) post publisher — thin adapter over the social_uploader infrastructure.

Publishes generated content to a stock's discussion page on Xueqiu using
Playwright with saved cookies. Delegates the actual browser automation to
the XueqiuUploader class from social_uploader/xueqiu_uploader/.

Usage:
    from platforms.xueqiu.publish import publish

    success = publish(content, ticker="TSLA")
    success = publish(content, ticker="TSLA", dry_run=True)  # preview only

CLI:
    python publish.py TSLA "post content here"
    python publish.py TSLA "post content here" --dry-run
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Ensure the project root is importable ──────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Paths (from engine.config and skill conventions) ───────────────────
_SOCIAL_UPLOADER_DIR = Path(os.path.expanduser(
    "~/Downloads/add-caption/social_uploader"
))
_XUEQIU_COOKIE_PATH = (
    _SOCIAL_UPLOADER_DIR / "xueqiu_uploader" / "xueqiu_account.json"
)
_XUEQIU_POST_URL = "https://xueqiu.com/S/{ticker}"


class _Logger:
    """Minimal logger matching the pattern in xueqiu-hottopics skill."""

    @staticmethod
    def info(msg: str) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [xueqiu/publish] {msg}")

    @staticmethod
    def success(msg: str) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [xueqiu/publish] OK: {msg}")

    @staticmethod
    def error(msg: str) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [xueqiu/publish] ERROR: {msg}")


_log = _Logger()


def _ensure_uploader_importable() -> None:
    """
    Add social_uploader to sys.path so we can import XueqiuUploader.
    Follows the same pattern as ~/clawd/skills/xueqiu-hottopics/xueqiu_hottopics.py.
    """
    uploader_dir = str(_SOCIAL_UPLOADER_DIR)
    if uploader_dir not in sys.path:
        sys.path.insert(0, uploader_dir)


async def _check_login(cookie_file: str) -> bool:
    """
    Verify that the saved Xueqiu cookies are still valid.

    Returns True if logged in, False otherwise.
    """
    _ensure_uploader_importable()

    try:
        from xueqiu_uploader.main import xueqiu_setup
        return await xueqiu_setup(cookie_file, handle=False)
    except ImportError:
        _log.error(
            "Cannot import xueqiu_uploader. "
            f"Ensure {_SOCIAL_UPLOADER_DIR} exists and contains xueqiu_uploader/"
        )
        return False
    except Exception as e:
        _log.error(f"Login check failed: {e}")
        return False


async def _publish_async(content: str, ticker: str, images: Optional[list[Path]] = None) -> bool:
    """
    Async implementation: post content to the ticker's Xueqiu discussion page.
    If images are provided, uploads them via the discussion editor's image upload.
    """
    cookie_file = str(_XUEQIU_COOKIE_PATH)

    # Verify login state
    if not await _check_login(cookie_file):
        _log.error(
            "Xueqiu cookies are invalid or expired. "
            "Re-login by running: python -c \""
            "import asyncio; "
            "from xueqiu_uploader.main import get_xueqiu_cookie; "
            f"asyncio.run(get_xueqiu_cookie('{cookie_file}'))\""
        )
        return False

    _ensure_uploader_importable()

    if images:
        return await _publish_with_images_async(content, ticker, images, cookie_file)

    try:
        from xueqiu_uploader.main import XueqiuUploader

        uploader = XueqiuUploader(cookie_file)
        await uploader.post_to_ticker(ticker.upper(), content)

        target_url = _XUEQIU_POST_URL.format(ticker=ticker.upper())
        _log.success(f"Published to {target_url}")
        return True

    except Exception as e:
        _log.error(f"Publishing failed: {e}")
        return False


async def _publish_with_images_async(
    content: str, ticker: str, images: list[Path], cookie_file: str
) -> bool:
    """
    Publish content with images via Xueqiu's discussion editor.

    Uses Playwright directly to:
    1. Navigate to the ticker page
    2. Focus the editor
    3. Upload images via the file chooser
    4. Insert text content
    5. Click publish
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        _log.error("playwright not installed for image publishing")
        return False

    import json

    target_url = _XUEQIU_POST_URL.format(ticker=ticker.upper())

    try:
        # Load cookies
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookies_data = json.load(f)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()

            # Add cookies
            if isinstance(cookies_data, list):
                await context.add_cookies(cookies_data)
            elif isinstance(cookies_data, dict) and "cookies" in cookies_data:
                await context.add_cookies(cookies_data["cookies"])

            page = await context.new_page()
            await page.goto(target_url, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # Find and focus the editor
            editor = await page.query_selector(".lite-editor__textarea")
            if not editor:
                # Try alternate selectors
                editor = await page.query_selector("[contenteditable='true']")
            if not editor:
                editor = await page.query_selector("textarea")

            if not editor:
                _log.error("Could not find editor element on page")
                await browser.close()
                return False

            await editor.click()
            await page.wait_for_timeout(500)

            # Upload images via file chooser
            valid_images = [img for img in images if img.exists()]
            if valid_images:
                _log.info(f"Uploading {len(valid_images)} images")

                # Look for image upload button in toolbar
                img_btn = await page.query_selector(
                    ".lite-editor__toolbar .image-btn, "
                    ".lite-editor__toolbar [data-type='image'], "
                    ".lite-editor__toolbar button[title*='图'], "
                    ".lite-editor__toolbar .icon-image"
                )

                if img_btn:
                    for img_path in valid_images:
                        async with page.expect_file_chooser() as fc_info:
                            await img_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(str(img_path))
                        await page.wait_for_timeout(2000)
                        _log.info(f"Uploaded image: {img_path.name}")
                else:
                    _log.warning("No image upload button found — posting text only")

            # Insert text content
            await editor.click()
            await page.wait_for_timeout(300)
            await page.keyboard.type(content, delay=10)
            await page.wait_for_timeout(1000)

            # Click publish button
            publish_btn = await page.query_selector(
                "button.lite-editor__submit, "
                "button[class*='submit'], "
                "a.lite-editor__submit"
            )
            if publish_btn:
                await publish_btn.click()
                await page.wait_for_timeout(3000)
                _log.success(f"Published with images to {target_url}")
            else:
                _log.error("Could not find publish button")
                await browser.close()
                return False

            await browser.close()
            return True

    except Exception as e:
        _log.error(f"Image publishing failed: {e}")
        return False


def publish(
    content: str,
    ticker: str,
    dry_run: bool = False,
    images: Optional[list[Path]] = None,
) -> bool:
    """
    Publish content to a stock's discussion page on Xueqiu.

    This is the main entry point for the publishing adapter. It handles
    cookie validation, browser automation via Playwright, and posting
    to https://xueqiu.com/S/{TICKER}.

    Args:
        content: The post text to publish (plain text, no markdown).
        ticker: Stock ticker symbol (e.g. "TSLA", "AAPL").
        dry_run: If True, prints the content and target URL without publishing.
        images: Optional list of image file paths to upload with the post.

    Returns:
        True if the post was published (or dry_run succeeded), False on error.
    """
    ticker = ticker.upper()
    target_url = _XUEQIU_POST_URL.format(ticker=ticker)

    if dry_run:
        print("\n" + "=" * 60)
        print(f"[DRY RUN] Target: {target_url}")
        print("=" * 60)
        print(content)
        if images:
            print(f"\n[DRY RUN] Images ({len(images)}):")
            for img in images:
                print(f"  - {img}")
        print("=" * 60)
        print(f"[DRY RUN] {len(content)} chars | Would publish to {target_url}")
        print("=" * 60 + "\n")
        return True

    img_count = len(images) if images else 0
    _log.info(f"Publishing to {target_url} ({len(content)} chars, {img_count} images)")

    # Run the async publisher in a new event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(
                asyncio.run, _publish_async(content, ticker, images)
            ).result()
        return result
    else:
        return asyncio.run(_publish_async(content, ticker, images))


# ── CLI entry point ────────────────────────────────────────────────────

def _cli() -> None:
    """CLI: python publish.py <TICKER> <CONTENT> [--dry-run]"""
    import argparse

    parser = argparse.ArgumentParser(description="Publish content to Xueqiu stock discussion")
    parser.add_argument("ticker", help="Stock ticker (e.g. TSLA, AAPL)")
    parser.add_argument("content", nargs="?", default=None, help="Post content (or reads from stdin)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without publishing")
    parser.add_argument(
        "--file", "-f", type=str, default=None,
        help="Read content from a file instead of argument",
    )
    args = parser.parse_args()

    # Determine content source
    content: Optional[str] = None
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        content = file_path.read_text(encoding="utf-8").strip()
    elif args.content:
        content = args.content
    else:
        # Try reading from stdin
        if not sys.stdin.isatty():
            content = sys.stdin.read().strip()

    if not content:
        print("Error: No content provided. Pass as argument, --file, or pipe to stdin.")
        sys.exit(1)

    success = publish(content, ticker=args.ticker, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    _cli()
