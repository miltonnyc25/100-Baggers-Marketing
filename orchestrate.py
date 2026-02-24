#!/usr/bin/env python3
"""
100Baggers Report Marketing Orchestrator

One-command pipeline: report → parse → generate platform content → (optional) publish.

Usage:
    python orchestrate.py SMCI                          # All platforms, dry-run
    python orchestrate.py SMCI --platforms xueqiu       # Single platform
    python orchestrate.py SMCI --publish                # Generate + publish
    python orchestrate.py --all --dry-run               # All tickers, preview
    python orchestrate.py --list                        # List available tickers
"""

import argparse
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import (
    AVAILABLE_TICKERS,
    find_english_html_report,
    find_english_markdown,
    find_html_report,
    find_markdown_report,
)
from engine.markdown_parser import MarkdownReportParser
from engine.report_parser import HTMLReportParser
from engine.report_schema import ReportData

# ── Constants ─────────────────────────────────────────────────────────

ALL_PLATFORMS = ["xueqiu", "xiaohongshu", "twitter", "youtube"]

PLATFORM_LABELS = {
    "xueqiu": "雪球",
    "xiaohongshu": "小红书",
    "twitter": "X/Twitter",
    "youtube": "YouTube",
}


# ── Helpers ───────────────────────────────────────────────────────────


class Log:
    @staticmethod
    def info(msg: str) -> None:
        print(f"[{datetime.now():%H:%M:%S}] ℹ️  {msg}")

    @staticmethod
    def ok(msg: str) -> None:
        print(f"[{datetime.now():%H:%M:%S}] ✅ {msg}")

    @staticmethod
    def warn(msg: str) -> None:
        print(f"[{datetime.now():%H:%M:%S}] ⚠️  {msg}")

    @staticmethod
    def err(msg: str) -> None:
        print(f"[{datetime.now():%H:%M:%S}] ❌ {msg}")


_PLATFORM_LANGUAGE = {
    "xueqiu": "zh",
    "xiaohongshu": "zh",
    "twitter": "en",
    "youtube": "en",
}


def load_report(ticker: str, language: str = "zh") -> ReportData | None:
    """Parse a report for *ticker*, preferring HTML (reflects manual edits) over Markdown."""
    try:
        html_parser = HTMLReportParser()
    except ImportError:
        html_parser = None
        Log.warn("beautifulsoup4 not installed — HTML parsing unavailable")

    if language == "en" and html_parser:
        html_path = find_english_html_report(ticker)
        if html_path:
            Log.info(f"Parsing English HTML: {html_path}")
            return html_parser.parse(html_path)

    if html_parser:
        html_path = find_html_report(ticker)
        if html_path:
            Log.info(f"Parsing HTML: {html_path.name}")
            return html_parser.parse(html_path)

    # Fallback to Markdown
    if language == "en":
        md_path = find_english_markdown(ticker)
        if md_path:
            Log.info(f"Parsing English Markdown: {md_path.name}")
            return MarkdownReportParser().parse(md_path)

    md_path = find_markdown_report(ticker)
    if md_path:
        Log.info(f"Parsing Markdown (fallback): {md_path.name}")
        return MarkdownReportParser().parse(md_path)

    Log.err(f"No report found for {ticker}")
    return None


def get_platform_module(platform: str):
    """Dynamically import platforms/{platform}/generate.py."""
    mod_name = f"platforms.{platform}.generate"
    try:
        return importlib.import_module(mod_name)
    except ImportError as e:
        Log.err(f"Cannot import {mod_name}: {e}")
        return None


def get_publish_module(platform: str):
    """Dynamically import platforms/{platform}/publish.py."""
    mod_name = f"platforms.{platform}.publish"
    try:
        return importlib.import_module(mod_name)
    except ImportError as e:
        Log.err(f"Cannot import {mod_name}: {e}")
        return None


# ── Core pipeline ─────────────────────────────────────────────────────


def process_ticker(
    ticker: str,
    platforms: list[str],
    publish: bool = False,
    dry_run: bool = True,
) -> dict[str, bool]:
    """Run the full pipeline for one ticker. Returns {platform: success}."""

    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()
    results: dict[str, bool] = {}

    print()
    print("=" * 60)
    print(f"  {ticker_upper} — Report Marketing Pipeline")
    print("=" * 60)

    # 1. Load & parse report
    report = load_report(ticker_lower)
    if not report:
        return {p: False for p in platforms}

    Log.ok(
        f"Parsed {ticker_upper}: "
        f"{len(report.chapters)} chapters, "
        f"{len(report.key_findings)} findings"
    )

    # 2. Generate content for each platform
    for platform in platforms:
        label = PLATFORM_LABELS.get(platform, platform)
        print(f"\n--- {label} ({platform}) ---")

        gen_mod = get_platform_module(platform)
        if not gen_mod:
            results[platform] = False
            continue

        try:
            archive_dir = PROJECT_ROOT / "platforms" / platform / "archive" / ticker_lower
            archive_dir.mkdir(parents=True, exist_ok=True)

            output_path = gen_mod.generate_to_file(report, archive_dir)
            Log.ok(f"Content saved: {output_path}")

            # 3. Optionally publish
            if publish and not dry_run:
                results[platform] = _publish_platform(
                    platform, output_path, ticker_upper, report
                )
            else:
                if dry_run:
                    _preview_output(platform, output_path)
                results[platform] = True

        except Exception as e:
            Log.err(f"{label} failed: {e}")
            results[platform] = False

    return results


def _preview_output(platform: str, output_path: Path) -> None:
    """Print a preview of the generated content."""
    if output_path.is_dir():
        # YouTube returns a directory — show the script file
        for f in sorted(output_path.glob("*_youtube_script.md")):
            content = f.read_text(encoding="utf-8")
            preview = content[:500] + ("..." if len(content) > 500 else "")
            print(f"\n📄 Preview ({f.name}):\n{preview}\n")
            return
        # Fallback: show first .md or .txt file
        for f in sorted(output_path.iterdir()):
            if f.suffix in (".md", ".txt"):
                content = f.read_text(encoding="utf-8")
                preview = content[:500] + ("..." if len(content) > 500 else "")
                print(f"\n📄 Preview ({f.name}):\n{preview}\n")
                return
    else:
        content = output_path.read_text(encoding="utf-8")
        preview = content[:500] + ("..." if len(content) > 500 else "")
        print(f"\n📄 Preview:\n{preview}\n")


def _publish_platform(
    platform: str, output_path: Path, ticker: str, report: ReportData
) -> bool:
    """
    Dispatch to the correct platform publisher with the right arguments.

    Each platform has a different publish interface:
      - xueqiu:      publish(content: str, ticker, dry_run)
      - twitter:      publish(content: str, ticker, dry_run)
      - xiaohongshu:  publish(content_dir: Path, ticker, dry_run)
      - youtube:      publish(video_path, title, description, tags, dry_run)
    """
    pub_mod = get_publish_module(platform)
    if not pub_mod:
        return False

    label = PLATFORM_LABELS.get(platform, platform)
    Log.info(f"Publishing to {label}...")

    if platform in ("xueqiu", "twitter"):
        # Text-based platforms: read the file content and publish
        content = output_path.read_text(encoding="utf-8")
        return pub_mod.publish(content=content, ticker=ticker, dry_run=False)

    elif platform == "xiaohongshu":
        # XHS expects a directory with slides/video + caption
        content_dir = output_path.parent if output_path.is_file() else output_path
        return pub_mod.publish(content_dir=content_dir, ticker=ticker, dry_run=False)

    elif platform == "youtube":
        # YouTube needs a video file — generate only produces script/description.
        # Publishing requires a pre-rendered video. Log a message and skip.
        Log.warn(
            f"YouTube publishing requires a rendered video file. "
            f"Script saved at: {output_path}. "
            f"Render the video first, then publish manually with: "
            f"python platforms/youtube/publish.py <video.mp4> --title '...' -d <desc.md>"
        )
        return False

    else:
        Log.err(f"Unknown platform: {platform}")
        return False


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="100Baggers Report Marketing Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python orchestrate.py SMCI                        # All platforms, dry-run
  python orchestrate.py SMCI --platforms xueqiu     # Single platform
  python orchestrate.py SMCI --publish              # Generate + publish
  python orchestrate.py --all                       # All tickers, dry-run
  python orchestrate.py --list                      # List available tickers
""",
    )
    parser.add_argument("ticker", nargs="?", help="Stock ticker (e.g. SMCI)")
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=ALL_PLATFORMS,
        default=ALL_PLATFORMS,
        help="Platforms to generate for (default: all)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually publish (default: dry-run only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Generate content without publishing (default)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all available tickers",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available report tickers and exit",
    )

    args = parser.parse_args()

    # --list
    if args.list:
        print("Available tickers:")
        for t in sorted(AVAILABLE_TICKERS):
            md = find_markdown_report(t)
            status = "✅ .md" if md else "📄 .html only"
            print(f"  {t.upper():6s}  {status}")
        return

    # Determine tickers
    if args.all:
        tickers = AVAILABLE_TICKERS
    elif args.ticker:
        tickers = [args.ticker.lower()]
    else:
        parser.print_help()
        return

    dry_run = not args.publish

    print()
    print("🚀 100Baggers Report Marketing Pipeline")
    print(f"   Tickers:   {', '.join(t.upper() for t in tickers)}")
    print(f"   Platforms: {', '.join(args.platforms)}")
    print(f"   Mode:      {'DRY-RUN (preview only)' if dry_run else '🔴 LIVE PUBLISH'}")
    print()

    # Process each ticker
    all_results: dict[str, dict[str, bool]] = {}
    for ticker in tickers:
        all_results[ticker] = process_ticker(
            ticker=ticker,
            platforms=args.platforms,
            publish=args.publish,
            dry_run=dry_run,
        )

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    for ticker, results in all_results.items():
        success = sum(1 for v in results.values() if v)
        total = len(results)
        print(f"  {ticker.upper():6s}  {success}/{total} platforms OK")
        for platform, ok in results.items():
            icon = "✅" if ok else "❌"
            print(f"         {icon} {PLATFORM_LABELS.get(platform, platform)}")
    print()


if __name__ == "__main__":
    main()
