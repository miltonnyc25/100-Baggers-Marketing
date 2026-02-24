#!/usr/bin/env python3
"""
YouTube publishing adapter.

Publishes a video to YouTube by delegating to the existing skill publishers:
  1. ~/clawd/skills/earnings-video/youtube_publisher.py  (preferred -- full featured)
  2. ~/clawd/skills/youtube-daily-news/youtube_publisher.py  (fallback -- simpler)

Both skills share the same YouTube OAuth credentials managed by:
  ~/clawd/skills/youtube-auth/youtube_oauth.txt

Usage (as module):
    from platforms.youtube.publish import publish
    publish(video_path, title, description, tags, dry_run=False)

Usage (CLI):
    python platforms/youtube/publish.py <video_path> --title "..." --description-file desc.md
    python platforms/youtube/publish.py <video_path> --title "..." --dry-run
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Resolve project root ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import CLAWD_SKILLS_DIR, VENV_PYTHON

# ── Skill publisher paths (in order of preference) ────────────────────

EARNINGS_VIDEO_PUBLISHER = CLAWD_SKILLS_DIR / "earnings-video" / "youtube_publisher.py"
DAILY_NEWS_PUBLISHER = CLAWD_SKILLS_DIR / "youtube-daily-news" / "youtube_publisher.py"

# ── OAuth credential paths (checked in order) ─────────────────────────

OAUTH_PATHS = [
    CLAWD_SKILLS_DIR / "youtube-auth" / "youtube_oauth.txt",
    CLAWD_SKILLS_DIR / "earnings-video" / "youtube_credentials" / "youtube_oauth.txt",
]

# ── Platform config ───────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    CONFIG = json.load(_f)

DISCLAIMER = CONFIG["compliance"]["required_disclaimer"]


def _log(level: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"info": "INFO", "ok": " OK ", "warn": "WARN", "err": " ERR"}
    print(f"[{ts}] [{prefix.get(level, 'INFO')}] {msg}")


def _find_oauth_file() -> Optional[Path]:
    """Locate the YouTube OAuth credentials file."""
    # Check environment variable first
    env_val = os.environ.get("YOUTUBE_OAUTH_B64")
    if env_val:
        _log("info", "YouTube credentials found via YOUTUBE_OAUTH_B64 env var")
        return None  # Signal that env var is set, no file needed

    for p in OAUTH_PATHS:
        if p.exists():
            _log("info", f"YouTube credentials found: {p}")
            return p

    _log("err", "No YouTube OAuth credentials found.")
    _log("err", "Expected locations:")
    for p in OAUTH_PATHS:
        _log("err", f"  - {p}")
    _log("err", "Or set YOUTUBE_OAUTH_B64 environment variable.")
    return None


def _find_publisher() -> Optional[Path]:
    """Locate the best available YouTube publisher script."""
    if EARNINGS_VIDEO_PUBLISHER.exists():
        _log("info", f"Using publisher: {EARNINGS_VIDEO_PUBLISHER}")
        return EARNINGS_VIDEO_PUBLISHER
    if DAILY_NEWS_PUBLISHER.exists():
        _log("info", f"Using publisher: {DAILY_NEWS_PUBLISHER}")
        return DAILY_NEWS_PUBLISHER

    _log("err", "No YouTube publisher script found.")
    _log("err", "Expected locations:")
    _log("err", f"  - {EARNINGS_VIDEO_PUBLISHER}")
    _log("err", f"  - {DAILY_NEWS_PUBLISHER}")
    return None


def _ensure_disclaimer(description: str) -> str:
    """Append compliance disclaimer if not already present."""
    if DISCLAIMER not in description:
        description = description.rstrip() + f"\n\n{DISCLAIMER}"
    return description


def _publish_via_earnings_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "unlisted",
) -> bool:
    """
    Publish using the earnings-video publisher (direct Python import).

    This publisher has richer features: thumbnail generation, Gemini
    translation, token refresh with save-back.
    """
    publisher_dir = EARNINGS_VIDEO_PUBLISHER.parent
    if str(publisher_dir) not in sys.path:
        sys.path.insert(0, str(publisher_dir))

    try:
        # Import the upload function directly
        from youtube_publisher import upload_to_youtube

        _log("info", "Publishing via earnings-video youtube_publisher (direct import)...")
        video_id = upload_to_youtube(
            video_path=str(video_path),
            title=title,
            description=description,
            privacy=privacy,
        )

        if video_id:
            _log("ok", f"Published: https://youtu.be/{video_id}")
            return True
        else:
            _log("err", "Upload returned no video ID")
            return False

    except ImportError as exc:
        _log("warn", f"Direct import failed ({exc}), falling back to subprocess")
        return False
    finally:
        # Clean up sys.path
        if str(publisher_dir) in sys.path:
            sys.path.remove(str(publisher_dir))


def _publish_via_subprocess(
    publisher_path: Path,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "unlisted",
) -> bool:
    """
    Publish using a publisher script via subprocess.

    Works with both earnings-video and youtube-daily-news publishers.
    """
    # Write description to a temp file (both publishers accept file paths)
    desc_file = video_path.parent / f"{video_path.stem}_yt_description.tmp.md"
    desc_file.write_text(description, encoding="utf-8")

    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

    if publisher_path == DAILY_NEWS_PUBLISHER:
        # youtube-daily-news publisher CLI:
        #   python youtube_publisher.py <video_path> <title> --description <desc_file>
        cmd = [
            python,
            str(publisher_path),
            str(video_path),
            title,
            "--description", str(desc_file),
            "--tags",
        ] + tags

        if privacy == "private":
            cmd.append("--private")
        elif privacy == "unlisted":
            cmd.append("--unlisted")

    else:
        # earnings-video publisher CLI:
        #   python youtube_publisher.py <symbol> <quarter> <video_path>
        # This publisher generates its own metadata, so we use subprocess
        # only as a last resort. Prefer direct import above.
        cmd = [
            python,
            str(publisher_path),
            "CUSTOM",  # symbol placeholder
            "custom",  # quarter placeholder
            str(video_path),
        ]

    _log("info", f"Running: {' '.join(cmd[:4])}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout for video upload
            cwd=str(publisher_path.parent),
        )

        if result.returncode == 0:
            _log("ok", "Publisher subprocess completed successfully")
            if result.stdout:
                _log("info", result.stdout[-500:])
            return True
        else:
            _log("err", f"Publisher exited with code {result.returncode}")
            if result.stderr:
                _log("err", result.stderr[-500:])
            return False

    except subprocess.TimeoutExpired:
        _log("err", "Publisher timed out after 600 seconds")
        return False
    except Exception as exc:
        _log("err", f"Subprocess failed: {exc}")
        return False
    finally:
        # Clean up temp description file
        if desc_file.exists():
            desc_file.unlink()


# ── Public API ────────────────────────────────────────────────────────


def publish(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    dry_run: bool = False,
    privacy: str = "unlisted",
) -> bool:
    """
    Publish a video to YouTube.

    Args:
        video_path:   Path to the video file (mp4).
        title:        Video title (max 100 chars for YouTube API).
        description:  Video description text.
        tags:         List of tags for discoverability.
        dry_run:      If True, print metadata without uploading.
        privacy:      "public", "unlisted", or "private".

    Returns:
        True if published (or dry-run printed) successfully, False otherwise.
    """
    video_path = Path(video_path).resolve()
    tags = tags or []

    # Validate inputs
    if not video_path.exists():
        _log("err", f"Video file not found: {video_path}")
        return False

    if not video_path.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        _log("warn", f"Unexpected video format: {video_path.suffix}")

    # Enforce title length (YouTube API limit)
    if len(title) > 100:
        title = title[:97] + "..."
        _log("warn", f"Title truncated to 100 chars: {title}")

    # Ensure compliance disclaimer
    description = _ensure_disclaimer(description)

    # ── Dry run ───────────────────────────────────────────────────────
    if dry_run:
        _log("info", "=" * 60)
        _log("info", "DRY RUN -- No upload will be performed")
        _log("info", "=" * 60)
        _log("info", f"Video:       {video_path}")
        _log("info", f"Title:       {title}")
        _log("info", f"Privacy:     {privacy}")
        _log("info", f"Tags:        {', '.join(tags)}")
        _log("info", f"Description: ({len(description)} chars)")
        _log("info", "-" * 60)
        print(description)
        _log("info", "-" * 60)
        _log("ok", "Dry run complete.")
        return True

    # ── Pre-flight checks ─────────────────────────────────────────────
    oauth_file = _find_oauth_file()
    # oauth_file is None either when env var is set OR when no creds found.
    # We differentiate by checking the env var.
    if oauth_file is None and not os.environ.get("YOUTUBE_OAUTH_B64"):
        _log("err", "Cannot publish: no YouTube credentials available")
        return False

    publisher_path = _find_publisher()
    if publisher_path is None:
        _log("err", "Cannot publish: no publisher script available")
        return False

    # ── Attempt 1: direct import (earnings-video only) ────────────────
    if publisher_path == EARNINGS_VIDEO_PUBLISHER:
        success = _publish_via_earnings_video(
            video_path, title, description, tags, privacy
        )
        if success:
            return True
        _log("warn", "Direct import failed, trying subprocess fallback...")

    # ── Attempt 2: subprocess ─────────────────────────────────────────
    return _publish_via_subprocess(
        publisher_path, video_path, title, description, tags, privacy
    )


# ── CLI entrypoint ────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Publish a video to YouTube via 100Baggers skill publishers."
    )
    parser.add_argument("video_path", type=Path, help="Path to the video file")
    parser.add_argument("--title", "-t", required=True, help="Video title")
    parser.add_argument(
        "--description", "-d",
        help="Description text or path to a .md file",
    )
    parser.add_argument(
        "--description-file",
        type=Path,
        help="Path to description file (alternative to --description)",
    )
    parser.add_argument("--tags", nargs="+", default=[], help="Tags for the video")
    parser.add_argument(
        "--privacy",
        choices=["public", "unlisted", "private"],
        default="unlisted",
        help="Video privacy status (default: unlisted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print metadata without uploading",
    )

    args = parser.parse_args()

    # Resolve description
    description = ""
    if args.description_file and args.description_file.exists():
        description = args.description_file.read_text(encoding="utf-8")
    elif args.description:
        if Path(args.description).exists():
            description = Path(args.description).read_text(encoding="utf-8")
        else:
            description = args.description
    else:
        description = f"{args.title}\n\n{DISCLAIMER}"

    success = publish(
        video_path=args.video_path,
        title=args.title,
        description=description,
        tags=args.tags,
        dry_run=args.dry_run,
        privacy=args.privacy,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
