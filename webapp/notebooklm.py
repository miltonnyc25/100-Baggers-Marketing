"""
NotebookLM video generation for report segments.

Wraps the existing NotebookLM service infrastructure to generate
per-segment videos with branded visual styles.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Paths to existing building blocks
_ADD_CAPTION_DIR = Path(os.path.expanduser("~/Downloads/add-caption"))
_NLM_VIDEO_DIR = _ADD_CAPTION_DIR / "notebooklm_video"
_CLAWD_SKILLS = Path(os.path.expanduser("~/clawd/skills"))
_DAILY_READS = _CLAWD_SKILLS / "daily-reads"
_XHS_PUBLISH = _CLAWD_SKILLS / "xiaohongshu-publish"

# Add building block paths for imports
for _p in [str(_NLM_VIDEO_DIR), str(_DAILY_READS), str(_XHS_PUBLISH), str(_ADD_CAPTION_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def generate_segment_video(session, segment) -> Path | None:
    """
    Generate a NotebookLM video for a report segment.

    Steps:
    1. Write segment content to a temp file as source material
    2. Create a NotebookLM task via the service
    3. Wait for video generation + download
    4. Post-process: trim + transcribe + subtitles + logo

    Returns the path to the processed video, or None on failure.
    """
    from webapp.state import SessionState
    from engine.segment_schema import SegmentData

    ticker = session.ticker.upper()
    seg_id = segment.segment_id

    # Step 1: Write segment content to temp file
    work_dir = Path(tempfile.mkdtemp(prefix=f"nlm-{ticker}-{seg_id}-"))
    source_file = work_dir / f"{ticker}_{seg_id}_source.md"
    source_file.write_text(
        f"# {segment.title}\n\n{segment.content_markdown}",
        encoding="utf-8",
    )
    log.info("Wrote segment source to %s (%d chars)", source_file, len(segment.content_markdown))

    # Step 2: Create and process NotebookLM task
    try:
        video_path = _generate_via_service(source_file, work_dir, ticker, segment)
    except ImportError:
        log.warning("NotebookLM service not available, trying fallback")
        video_path = None

    if not video_path:
        log.warning("Video generation did not produce a file")
        return None

    # Step 3: Post-process (trim + subtitles + logo)
    try:
        processed = _postprocess_video(video_path, work_dir)
        return processed
    except Exception:
        log.exception("Video post-processing failed, returning raw video")
        return video_path


def _generate_via_service(source_file: Path, work_dir: Path, ticker: str, segment) -> Path | None:
    """Generate video using the NotebookLM service."""
    try:
        from notebooklm_service import NotebookLMService
    except ImportError:
        log.warning("notebooklm_service not importable")
        raise

    service = NotebookLMService()
    source_text = source_file.read_text(encoding="utf-8")

    # Build a steering prompt for this segment
    steering = _build_steering_prompt(ticker, segment)

    task = service.create_task(
        text_sources=[source_text],
        drive_links=[],
        question=f"Analyze {ticker}: {segment.title}",
        steering_prompt=steering,
        publish_targets=[],  # Don't auto-publish
        ticker=ticker,
    )

    log.info("Created NotebookLM task %s for %s/%s", task.task_id, ticker, segment.segment_id)

    # Process synchronously (called from a background thread)
    service.process_task(task.task_id)

    # Check result
    result = service.get_task(task.task_id)
    if result and result.video_path:
        return Path(result.video_path)
    if result and result.subtitle_video_path:
        return Path(result.subtitle_video_path)
    return None


def _postprocess_video(video_path: Path, work_dir: Path) -> Path:
    """Trim, transcribe, add subtitles and logo."""
    try:
        from process_notebooklm import process_video
        result = process_video(str(video_path), str(work_dir))
        processed = result.get("video")
        if processed and Path(processed).exists():
            return Path(processed)
    except ImportError:
        log.warning("process_notebooklm not available, trying video_processor")
        try:
            from video_processor import VideoSubtitleProcessor
            processor = VideoSubtitleProcessor()
            result = processor.process(str(video_path), str(work_dir))
            processed = result.get("video") or result.get("output")
            if processed and Path(processed).exists():
                return Path(processed)
        except ImportError:
            log.warning("No video processor available")

    return video_path


def _build_steering_prompt(ticker: str, segment) -> str:
    """Build a custom steering prompt for NotebookLM based on segment theme."""
    theme_prompts = {
        "executive_overview": (
            f"Provide a concise, high-level overview of {ticker}. Focus on the core "
            "investment thesis and key contradictions. Use an engaging, narrative style."
        ),
        "financial_deep_dive": (
            f"Dive deep into {ticker}'s financial metrics. Highlight revenue trends, "
            "margins, valuation multiples, and cash flow dynamics. Use specific numbers."
        ),
        "competitive_position": (
            f"Analyze {ticker}'s competitive moat and market position. Discuss barriers "
            "to entry, market share dynamics, and differentiation factors."
        ),
        "growth_technology": (
            f"Explore {ticker}'s growth drivers and technology advantages. Focus on "
            "product pipeline, innovation, and expansion opportunities."
        ),
        "risk_verdict": (
            f"Examine the key risks facing {ticker}. Present both bull and bear cases "
            "with supporting data. End with a balanced verdict."
        ),
    }

    # Handle merged themes
    base_theme = segment.theme.split("_")[0] if "_" in segment.theme else segment.theme
    for key in theme_prompts:
        if base_theme in key or segment.theme == key:
            return theme_prompts[key]

    return f"Analyze this segment about {ticker}: {segment.title}"
