#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaohongshu (小红书) publisher — thin adapter around existing skills.

Delegates the actual browser automation to:
  - ~/clawd/skills/xiaohongshu-slides/xhs_slides_publisher.py  (slide decks)
  - ~/clawd/skills/xiaohongshu-publish/xhs_publisher.py         (video posts)

This module adds:
  - Compliance checking (sensitive-topic filter) before publish
  - --dry-run mode for safe testing
  - Unified publish() interface consumed by the marketing orchestrator
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ── Resolve project root so engine imports work ──────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.config import VENV_PYTHON, CLAWD_SKILLS_DIR

# ── Platform config ──────────────────────────────────────────────────

_PLATFORM_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _PLATFORM_DIR / "config.json"

with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    PLATFORM_CONFIG: dict = json.load(_f)

SENSITIVE_TOPICS: list[str] = PLATFORM_CONFIG["compliance"]["sensitive_topics"]

# ── Skill script paths ───────────────────────────────────────────────

SLIDES_PUBLISHER = CLAWD_SKILLS_DIR / "xiaohongshu-slides" / "xhs_slides_publisher.py"
VIDEO_PUBLISHER = CLAWD_SKILLS_DIR / "xiaohongshu-publish" / "xhs_publisher.py"


# =====================================================================
# Compliance
# =====================================================================

def _check_compliance(content_dir: Path) -> list[str]:
    """
    Scan all .md and .txt files in content_dir for sensitive topics.

    Returns:
        list of violation descriptions (empty means all clear).
    """
    violations: list[str] = []

    for ext in ("*.md", "*.txt"):
        for fp in content_dir.glob(ext):
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for topic in SENSITIVE_TOPICS:
                if topic in text:
                    violations.append(
                        f"Sensitive topic '{topic}' found in {fp.name}"
                    )
    return violations


# =====================================================================
# Slide publishing
# =====================================================================

def _publish_slides(
    content_dir: Path,
    ticker: str,
    dry_run: bool = False,
) -> bool:
    """
    Publish a multi-image slide deck via xhs_slides_publisher.py.

    Expects content_dir to contain PNG images (the slides).
    """
    if not SLIDES_PUBLISHER.exists():
        print(f"[xiaohongshu/publish] ERROR: Slides publisher not found: {SLIDES_PUBLISHER}")
        return False

    # Find slide images
    slides = sorted(content_dir.glob("*.png"))
    if not slides:
        print(f"[xiaohongshu/publish] ERROR: No PNG slides found in {content_dir}")
        return False

    print(f"[xiaohongshu/publish] Found {len(slides)} slide images in {content_dir}")

    # The slides publisher expects a directory and a date string
    # Use today's date as fallback
    from datetime import date
    date_str = date.today().strftime("%Y-%m-%d")

    cmd = [
        str(VENV_PYTHON),
        str(SLIDES_PUBLISHER),
        str(content_dir),
        date_str,
    ]

    if dry_run:
        print(f"[xiaohongshu/publish] DRY RUN — would execute:")
        print(f"  {' '.join(cmd)}")
        return True

    print(f"[xiaohongshu/publish] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"[xiaohongshu/publish] ERROR: Slides publisher exited with code {result.returncode}")
        return False

    print(f"[xiaohongshu/publish] Slides published successfully")
    return True


# =====================================================================
# Video publishing
# =====================================================================

def _publish_video(
    content_dir: Path,
    ticker: str,
    dry_run: bool = False,
) -> bool:
    """
    Publish a video post via xhs_publisher.py.

    Expects content_dir to contain:
      - {ticker}*.mp4 or *.mp4  (video file)
      - *cover*.jpg             (cover image)
      - *xhs-post.md or *xiaohongshu.md  (post text)
    """
    if not VIDEO_PUBLISHER.exists():
        print(f"[xiaohongshu/publish] ERROR: Video publisher not found: {VIDEO_PUBLISHER}")
        return False

    # Find video
    videos = list(content_dir.glob("*.mp4"))
    if not videos:
        print(f"[xiaohongshu/publish] ERROR: No MP4 video found in {content_dir}")
        return False
    video_path = videos[0]

    # Find cover image
    covers = list(content_dir.glob("*cover*.jpg")) + list(content_dir.glob("*cover*.png"))
    if not covers:
        covers = list(content_dir.glob("*.jpg")) + list(content_dir.glob("*.png"))
    if not covers:
        print(f"[xiaohongshu/publish] ERROR: No cover image found in {content_dir}")
        return False
    cover_path = covers[0]

    # Find post markdown
    posts = (
        list(content_dir.glob("*xhs-post.md"))
        + list(content_dir.glob("*xiaohongshu.md"))
        + list(content_dir.glob("*.md"))
    )
    if not posts:
        print(f"[xiaohongshu/publish] ERROR: No post markdown found in {content_dir}")
        return False
    post_path = posts[0]

    cmd = [
        str(VENV_PYTHON),
        str(VIDEO_PUBLISHER),
        str(video_path),
        str(cover_path),
        str(post_path),
    ]

    if dry_run:
        print(f"[xiaohongshu/publish] DRY RUN — would execute:")
        print(f"  {' '.join(cmd)}")
        print(f"  Video: {video_path}")
        print(f"  Cover: {cover_path}")
        print(f"  Post:  {post_path}")
        return True

    print(f"[xiaohongshu/publish] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"[xiaohongshu/publish] ERROR: Video publisher exited with code {result.returncode}")
        return False

    print(f"[xiaohongshu/publish] Video published successfully")
    return True


# =====================================================================
# Public API
# =====================================================================

def publish(
    content_dir: Path,
    ticker: str,
    dry_run: bool = False,
    mode: Optional[str] = None,
) -> bool:
    """
    Publish content to Xiaohongshu.

    Automatically detects whether to use slide or video publishing based
    on the contents of content_dir, unless ``mode`` is explicitly set.

    Args:
        content_dir: Directory containing the content to publish.
        ticker:      Stock ticker (used for logging / file matching).
        dry_run:     If True, only print what would be done.
        mode:        Force "slides" or "video".  Auto-detected if None.

    Returns:
        True on success, False on failure.
    """
    content_dir = Path(content_dir)
    if not content_dir.is_dir():
        print(f"[xiaohongshu/publish] ERROR: Not a directory: {content_dir}")
        return False

    # ── Compliance check ─────────────────────────────────────────────
    violations = _check_compliance(content_dir)
    if violations:
        print("[xiaohongshu/publish] COMPLIANCE VIOLATIONS FOUND:")
        for v in violations:
            print(f"  - {v}")
        if not dry_run:
            print("[xiaohongshu/publish] Aborting publish due to compliance violations.")
            print("[xiaohongshu/publish] Fix the content or remove sensitive topics before retrying.")
            return False
        else:
            print("[xiaohongshu/publish] (dry-run: would abort)")

    # ── Detect mode ──────────────────────────────────────────────────
    if mode is None:
        has_video = bool(list(content_dir.glob("*.mp4")))
        has_slides = bool(list(content_dir.glob("*.png")))

        if has_video:
            mode = "video"
        elif has_slides:
            mode = "slides"
        else:
            print(f"[xiaohongshu/publish] ERROR: No video (.mp4) or slide images (.png) found in {content_dir}")
            return False

    print(f"[xiaohongshu/publish] Mode: {mode} | Ticker: {ticker.upper()} | Dry-run: {dry_run}")

    # ── Dispatch ─────────────────────────────────────────────────────
    if mode == "slides":
        return _publish_slides(content_dir, ticker, dry_run=dry_run)
    elif mode == "video":
        return _publish_video(content_dir, ticker, dry_run=dry_run)
    else:
        print(f"[xiaohongshu/publish] ERROR: Unknown mode '{mode}'. Use 'slides' or 'video'.")
        return False


# =====================================================================
# CLI
# =====================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Publish content to Xiaohongshu (小红书)"
    )
    parser.add_argument(
        "content_dir",
        help="Directory containing slides (PNG) or video (MP4) + cover + post.md",
    )
    parser.add_argument(
        "ticker",
        help="Stock ticker (e.g. tsla, aapl)",
    )
    parser.add_argument(
        "--mode",
        choices=["slides", "video"],
        default=None,
        help="Force slides or video mode (auto-detected by default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without actually publishing",
    )

    args = parser.parse_args()

    success = publish(
        content_dir=Path(os.path.expanduser(args.content_dir)),
        ticker=args.ticker,
        dry_run=args.dry_run,
        mode=args.mode,
    )

    sys.exit(0 if success else 1)
