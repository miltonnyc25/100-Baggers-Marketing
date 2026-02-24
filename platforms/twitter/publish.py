#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter/X publisher adapter.

Wraps the x-hottopics / x_uploader building blocks for publishing
tweets and threads from 100Baggers report content.

Building blocks:
    ~/Downloads/add-caption/social_uploader/x_uploader/main.py
        - XUploader   : Playwright-based tweet poster (headless mode)
        - x_setup     : Cookie validation helper

Cookie:
    ~/Downloads/add-caption/social_uploader/x_uploader/x_account.json

Usage:
    from platforms.twitter.publish import publish, publish_thread

    # Single post
    ok = publish("Your tweet text here", ticker="AAPL")

    # Thread (sequential tweets with delay)
    ok = publish_thread(["1/ First", "2/ Second", ...], ticker="AAPL")

    # Dry-run (preview without posting)
    ok = publish("Preview only", ticker="AAPL", dry_run=True)
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Paths ───────────────────────────────────────────────────────────────
SOCIAL_UPLOADER_DIR = Path(os.path.expanduser(
    "~/Downloads/add-caption/social_uploader"
))
X_COOKIE_PATH = SOCIAL_UPLOADER_DIR / "x_uploader" / "x_account.json"

# Delay between sequential thread tweets (seconds)
THREAD_TWEET_DELAY = 30


# ── Logging ─────────────────────────────────────────────────────────────

class _Logger:
    @staticmethod
    def info(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [twitter/publish] {msg}")

    @staticmethod
    def success(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [twitter/publish] OK: {msg}")

    @staticmethod
    def error(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [twitter/publish] ERROR: {msg}")

    @staticmethod
    def warning(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [twitter/publish] WARN: {msg}")


_log = _Logger()


# ── Uploader access ─────────────────────────────────────────────────────

def _ensure_uploader_on_path():
    """Add social_uploader to sys.path so x_uploader can be imported."""
    path_str = str(SOCIAL_UPLOADER_DIR)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _get_uploader():
    """
    Import and return (XUploader class, x_setup function).

    Raises ImportError with instructions if dependencies are missing.
    """
    _ensure_uploader_on_path()
    try:
        from x_uploader.main import XUploader, x_setup
        return XUploader, x_setup
    except ImportError as e:
        raise ImportError(
            f"Cannot import x_uploader: {e}\n"
            f"Ensure Playwright is installed:\n"
            f"  cd ~/Downloads/add-caption && source venv/bin/activate\n"
            f"  pip install playwright && playwright install chromium"
        ) from e


# ── Cookie validation ───────────────────────────────────────────────────

async def _validate_cookie() -> bool:
    """Check that the X cookie file exists and is accessible."""
    if not X_COOKIE_PATH.exists():
        _log.error(
            f"X cookie not found at {X_COOKIE_PATH}\n"
            "Run the login flow first:\n"
            "  cd ~/Downloads/add-caption/social_uploader\n"
            '  python -c "import asyncio; from x_uploader.main import get_x_cookie; '
            "asyncio.run(get_x_cookie('x_uploader/x_account.json'))\""
        )
        return False

    _, x_setup = _get_uploader()
    cookie_ok = await x_setup(str(X_COOKIE_PATH), handle=False)
    if not cookie_ok:
        _log.error("X cookie invalid or expired. Please re-login.")
        return False

    return True


# ── Single tweet publishing ─────────────────────────────────────────────

async def _post_single(text: str) -> bool:
    """Post a single tweet via XUploader (headless)."""
    XUploader, _ = _get_uploader()
    uploader = XUploader(str(X_COOKIE_PATH), headless=True)
    return await uploader.post_tweet(text)


def publish(
    content: str,
    ticker: str = "",
    dry_run: bool = False,
) -> bool:
    """
    Publish a single post to Twitter/X.

    Args:
        content:  The tweet / long-form post text.
        ticker:   Stock ticker (for logging only).
        dry_run:  If True, print the content without posting.

    Returns:
        True if the post was published (or dry-run succeeded), False otherwise.
    """
    label = f"${ticker.upper()}" if ticker else "tweet"
    word_count = len(content.split())
    char_count = len(content)

    _log.info(f"Publishing {label} ({word_count} words, {char_count} chars)")

    # Preview
    print(f"\n--- Tweet Preview ({label}) ---")
    print(content)
    print("--- End Preview ---\n")

    if dry_run:
        _log.info("[DRY-RUN] Skipping actual post")
        return True

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If called from within an async context, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run, _publish_async(content)
                ).result()
            return result
        else:
            return asyncio.run(_publish_async(content))
    except RuntimeError:
        return asyncio.run(_publish_async(content))


async def _publish_async(content: str) -> bool:
    """Async implementation of single-post publishing."""
    cookie_ok = await _validate_cookie()
    if not cookie_ok:
        return False

    success = await _post_single(content)
    if success:
        _log.success("Tweet posted successfully")
    else:
        _log.error("Failed to post tweet")
    return success


# ── Thread publishing ───────────────────────────────────────────────────

def publish_thread(
    tweets: list[str],
    ticker: str = "",
    dry_run: bool = False,
    delay: int = THREAD_TWEET_DELAY,
) -> bool:
    """
    Publish a tweet thread to Twitter/X.

    Posts tweets sequentially with a delay between each to avoid rate limits.
    Note: X's API does not support native threading via the compose page, so
    each tweet is posted independently. For true threading, tweets should
    include numbering (1/, 2/, ...) and the $TICKER cashtag for discoverability.

    Args:
        tweets:   List of tweet strings.
        ticker:   Stock ticker (for logging).
        dry_run:  If True, print all tweets without posting.
        delay:    Seconds to wait between tweets (default: 30).

    Returns:
        True if all tweets were posted, False if any failed.
    """
    label = f"${ticker.upper()}" if ticker else "thread"
    _log.info(f"Publishing thread {label} ({len(tweets)} tweets)")

    # Preview all tweets
    print(f"\n{'=' * 60}")
    print(f"Thread Preview: {label}")
    print(f"{'=' * 60}")
    for i, tweet in enumerate(tweets, 1):
        print(f"\n--- Tweet {i}/{len(tweets)} ({len(tweet)} chars) ---")
        print(tweet)
    print(f"\n{'=' * 60}\n")

    if dry_run:
        _log.info(f"[DRY-RUN] Skipping post of {len(tweets)} tweets")
        return True

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    _publish_thread_async(tweets, ticker, delay),
                ).result()
            return result
        else:
            return asyncio.run(
                _publish_thread_async(tweets, ticker, delay)
            )
    except RuntimeError:
        return asyncio.run(
            _publish_thread_async(tweets, ticker, delay)
        )


async def _publish_thread_async(
    tweets: list[str],
    ticker: str,
    delay: int,
) -> bool:
    """Async implementation of thread publishing."""
    cookie_ok = await _validate_cookie()
    if not cookie_ok:
        return False

    success_count = 0
    total = len(tweets)

    for i, tweet in enumerate(tweets, 1):
        _log.info(f"Posting tweet {i}/{total} ({len(tweet)} chars)...")

        ok = await _post_single(tweet)
        if ok:
            _log.success(f"Tweet {i}/{total} posted")
            success_count += 1
        else:
            _log.error(f"Tweet {i}/{total} failed")
            _log.warning(
                f"Stopping thread: {success_count}/{total} posted, "
                f"failed at tweet {i}"
            )
            return False

        # Wait between tweets (skip after the last one)
        if i < total:
            _log.info(f"Waiting {delay}s before next tweet...")
            await asyncio.sleep(delay)

    _log.success(f"Thread complete: {success_count}/{total} tweets posted")
    return success_count == total


# ── CLI entry point ─────────────────────────────────────────────────────

def _cli():
    """Standalone CLI for testing publish functionality."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Publish tweet(s) to X/Twitter"
    )
    parser.add_argument(
        "content",
        nargs="?",
        help="Tweet text (for single post mode)",
    )
    parser.add_argument(
        "--thread-file",
        type=Path,
        help="Path to a thread file (one tweet per paragraph, separated by blank lines)",
    )
    parser.add_argument(
        "--ticker", "-t",
        default="",
        help="Stock ticker for logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without posting",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=THREAD_TWEET_DELAY,
        help=f"Delay between thread tweets in seconds (default: {THREAD_TWEET_DELAY})",
    )
    args = parser.parse_args()

    if args.thread_file:
        # Thread mode: read file and split into tweets
        if not args.thread_file.exists():
            print(f"File not found: {args.thread_file}")
            sys.exit(1)
        text = args.thread_file.read_text(encoding="utf-8")
        # Skip comment lines (starting with #)
        paragraphs = text.strip().split("\n\n")
        tweets = [
            p.strip()
            for p in paragraphs
            if p.strip() and not p.strip().startswith("#")
        ]
        if not tweets:
            print("No tweets found in file")
            sys.exit(1)
        ok = publish_thread(
            tweets,
            ticker=args.ticker,
            dry_run=args.dry_run,
            delay=args.delay,
        )
    elif args.content:
        ok = publish(
            args.content,
            ticker=args.ticker,
            dry_run=args.dry_run,
        )
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _cli()
