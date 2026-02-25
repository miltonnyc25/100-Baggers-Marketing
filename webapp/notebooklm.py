"""
NotebookLM video generation for report segments.

Uses the NotebookLM CLI + Python SDK directly (article-to-video pipeline approach)
for reliable video generation with native language support (zh_Hans / en).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)

# Paths to existing building blocks
_ADD_CAPTION_DIR = Path(os.path.expanduser("~/Downloads/add-caption"))
_NLM_VIDEO_DIR = _ADD_CAPTION_DIR / "notebooklm_video"
_CLAWD_SKILLS = Path(os.path.expanduser("~/clawd/skills"))
_DAILY_READS = _CLAWD_SKILLS / "daily-reads"
_XHS_PUBLISH = _CLAWD_SKILLS / "xiaohongshu-publish"

# Add building block paths for imports (process_notebooklm, etc.)
for _p in [str(_XHS_PUBLISH), str(_NLM_VIDEO_DIR), str(_DAILY_READS), str(_ADD_CAPTION_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── NotebookLM CLI + SDK paths ──────────────────────────────────────
_NOTEBOOKLM_CLI = "/Library/Frameworks/Python.framework/Versions/3.12/bin/notebooklm"
_PYTHON_312 = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
_GENERATE_VIDEO_SCRIPT = _DAILY_READS / "generate_custom_video.py"
_NLM_STORAGE = Path(os.path.expanduser("~/.notebooklm/storage_state.json"))
_DAILY_READS_CREDS = _DAILY_READS / "notebooklm_credentials" / "storage_state.json"
_LOGO_PATH = _ADD_CAPTION_DIR / "assets" / "100bagersclub_logo.png"
_POLL_INTERVAL = 30   # seconds between status checks
_MAX_POLL_TIME = 3600  # max wait (60 min)
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


# ── Focus prompt (loaded from .md file) ─────────────────────────────

def _load_focus_prompt(ticker: str = "") -> str:
    """Load the default focus prompt from video_focus.md.

    This single prompt replaces the old per-theme steering prompts.
    The curated document (source material) already handles angle/theme
    selection — the focus prompt only tells the AI hosts *how* to discuss.
    """
    prompt_file = _PROMPTS_DIR / "video_focus.md"
    if not prompt_file.exists():
        log.warning("video_focus.md not found at %s, using fallback", prompt_file)
        return f"深入分析这份关于{ticker}的深度研究报告。引用具体数据，面向有经验的投资者。"

    text = prompt_file.read_text(encoding="utf-8")

    # Extract the content under "## 默认 Focus Prompt" heading
    marker = "## 默认 Focus Prompt"
    idx = text.find(marker)
    if idx == -1:
        log.warning("Could not find default prompt section in video_focus.md")
        return text.strip()

    # Skip the rest of the heading line, take content until the next "## "
    content = text[idx + len(marker):]
    first_newline = content.find("\n")
    if first_newline != -1:
        content = content[first_newline:]
    next_section = content.find("\n## ")
    if next_section != -1:
        content = content[:next_section]

    return content.strip()


# ── CLI helpers ─────────────────────────────────────────────────────

def _nlm_cli(*args, timeout=60) -> str:
    """Run a notebooklm CLI command and return stdout."""
    cmd = [_NOTEBOOKLM_CLI] + [str(a) for a in args]
    log.info("NLM CLI: %s", " ".join(str(a) for a in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        log.error("NLM CLI stderr: %s", result.stderr)
        raise RuntimeError(f"notebooklm CLI failed: {result.stderr}")
    return result.stdout.strip()


@contextlib.contextmanager
def _swap_credentials(creds_path: Path):
    """Context manager to temporarily swap NotebookLM credentials.

    Backs up current ~/.notebooklm/storage_state.json, copies in target
    credentials, and restores the original on exit (even on error).
    """
    backup = _NLM_STORAGE.with_suffix(".json.backup")
    if not creds_path.exists():
        log.warning("Credentials not found at %s, using default", creds_path)
        yield
        return
    try:
        if _NLM_STORAGE.exists():
            shutil.copy2(_NLM_STORAGE, backup)
            log.info("Backed up credentials to %s", backup)
        shutil.copy2(creds_path, _NLM_STORAGE)
        log.info("Switched credentials to %s", creds_path)
        yield
    finally:
        if backup.exists():
            shutil.copy2(backup, _NLM_STORAGE)
            backup.unlink()
            log.info("Restored original credentials")


def _create_notebook_and_add_source(title: str, source_file: Path) -> str:
    """Create a NotebookLM notebook, add source, wait for indexing.

    Returns the notebook ID.
    """
    _nlm_cli("create", title)
    time.sleep(2)

    # Get most-recently-created notebook ID
    output = _nlm_cli("list", "--json")
    data = json.loads(output)
    notebooks = data.get("notebooks", [])
    if not notebooks:
        raise RuntimeError("No notebooks found after creation")
    notebook_id = notebooks[0]["id"]
    log.info("Created notebook %s: %s", notebook_id, title)

    _nlm_cli("use", notebook_id)
    _nlm_cli("source", "add", str(source_file), timeout=120)
    log.info("Added source to notebook %s", notebook_id)

    # Wait for source indexing (custom video needs indexed sources)
    log.info("Waiting 30s for source indexing...")
    time.sleep(30)

    return notebook_id


def _generate_video_via_sdk(
    notebook_id: str, language: str, focus_prompt: str,
) -> None:
    """Start video generation using generate_custom_video.py via subprocess.

    This calls the Python 3.12 SDK directly with the custom visual style
    and focus prompt.  The function returns once the generation task has
    been *started* — caller must poll for completion.
    """
    cmd = [
        str(_PYTHON_312), str(_GENERATE_VIDEO_SCRIPT),
        notebook_id,
        "--language", language,
        "--focus-prompt", focus_prompt,
    ]
    log.info("Starting video generation: language=%s, notebook=%s", language, notebook_id)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log.error("generate_custom_video.py failed: %s", result.stderr)
        raise RuntimeError(f"Video generation failed: {result.stderr}")
    log.info("Video generation started: %s", result.stdout.strip())


def _poll_video_status() -> str:
    """Poll NotebookLM artifact status until completed/failed/timeout."""
    max_checks = _MAX_POLL_TIME // _POLL_INTERVAL
    for i in range(max_checks):
        try:
            output = _nlm_cli("artifact", "list", "--json")
            data = json.loads(output)
            artifacts = data.get("artifacts", [])
            status = artifacts[-1].get("status", "unknown") if artifacts else "unknown"
        except Exception:
            log.warning("Poll #%d: failed to check status", i + 1)
            status = "unknown"

        log.info("Poll #%d: artifact status = %s", i + 1, status)

        if status == "completed":
            return status
        if status == "failed":
            return status

        time.sleep(_POLL_INTERVAL)

    log.warning("Polling timed out after %ds", _MAX_POLL_TIME)
    return "timeout"


def _download_video(output_path: Path) -> Path | None:
    """Download the generated video from NotebookLM."""
    try:
        _nlm_cli("download", "video", str(output_path), "--force", timeout=300)
        if output_path.exists() and output_path.stat().st_size > 0:
            size_mb = output_path.stat().st_size / (1024 * 1024)
            log.info("Downloaded video: %s (%.1f MB)", output_path, size_mb)
            return output_path
    except Exception:
        log.exception("Video download failed")
    return None


# ── English Video Generation ────────────────────────────────────────

def generate_segment_video(session, segment) -> Path | None:
    """Generate a NotebookLM video for a report segment (English).

    Pipeline: create notebook → add source → generate video (en) →
    poll → download → post-process (trim + subtitles + logo).
    """
    ticker = session.ticker.upper()
    seg_id = segment.segment_id
    work_dir = Path(tempfile.mkdtemp(prefix=f"nlm-{ticker}-{seg_id}-"))

    source_file = work_dir / f"{ticker}_{seg_id}_source.md"
    source_file.write_text(
        f"# {segment.title}\n\n{segment.content_markdown}",
        encoding="utf-8",
    )
    log.info("Wrote segment source to %s (%d chars)", source_file, len(segment.content_markdown))

    try:
        video_path = _generate_via_cli(source_file, work_dir, ticker, segment, language="en")
    except Exception:
        log.exception("English video generation failed")
        video_path = None

    if not video_path:
        log.warning("Video generation did not produce a file")
        return None

    try:
        processed = _postprocess_video(video_path, work_dir)
        return processed
    except Exception:
        log.exception("Video post-processing failed, returning raw video")
        return video_path


def _generate_via_cli(
    source_file: Path, work_dir: Path, ticker: str, segment,
    language: str = "en",
) -> Path | None:
    """Generate video using the NotebookLM CLI + SDK pipeline."""
    title = f"{ticker} - {segment.title}"
    focus_prompt = _load_focus_prompt(ticker)

    try:
        notebook_id = _create_notebook_and_add_source(title, source_file)
        _generate_video_via_sdk(notebook_id, language, focus_prompt)
        status = _poll_video_status()

        if status != "completed":
            log.error("Video generation ended with status: %s", status)
            return None

        output_path = work_dir / f"{ticker}_{segment.segment_id}_raw.mp4"
        return _download_video(output_path)
    except Exception:
        log.exception("English CLI pipeline failed")
        return None


def _postprocess_video(video_path: Path, work_dir: Path) -> Path:
    """Trim, transcribe, add subtitles and logo (English videos)."""
    try:
        from process_notebooklm import process_video
        result = process_video(str(video_path), str(work_dir))
        processed = result.get("video")
        if processed and Path(processed).exists():
            return Path(processed)
    except ImportError:
        log.warning("process_notebooklm not available")

    return video_path


# ── Chinese Video Generation (XHS) ──────────────────────────────────

def generate_segment_video_chinese(session, segment) -> Path | None:
    """Generate a Chinese NotebookLM video for a report segment (XHS).

    Pipeline: swap creds → create notebook → add source (~1/3 content) →
    generate video (zh_Hans) → poll → download → restore creds →
    post-process (trim 2.5s + logo, no subtitles).
    """
    ticker = session.ticker.upper()
    seg_id = segment.segment_id
    work_dir = Path(tempfile.mkdtemp(prefix=f"nlm-zh-{ticker}-{seg_id}-"))

    # Trim source to ~1/3 at paragraph boundary
    full_text = segment.content_markdown
    target_len = max(len(full_text) // 3, 500)
    trimmed = _trim_to_paragraphs(full_text, target_len)

    source_file = work_dir / f"{ticker}_{seg_id}_zh_source.md"
    source_file.write_text(
        f"# {segment.title}\n\n{trimmed}",
        encoding="utf-8",
    )
    log.info("Wrote Chinese segment source (%d/%d chars) to %s",
             len(trimmed), len(full_text), source_file)

    try:
        video_path = _generate_zh_via_cli(source_file, work_dir, ticker, segment)
    except Exception:
        log.exception("Chinese video generation failed")
        return None

    if not video_path:
        log.warning("Chinese video generation did not produce a file")
        return None

    # Post-process: trim 2.5s + logo (no subtitles for Chinese audio)
    try:
        processed = _ffmpeg_trim_and_logo(video_path, work_dir)
        return processed
    except Exception:
        log.exception("Chinese video post-processing failed, returning raw video")
        return video_path


def _generate_zh_via_cli(
    source_file: Path, work_dir: Path, ticker: str, segment,
) -> Path | None:
    """Generate Chinese video using CLI + SDK.

    Tries daily-reads credentials first; if they fail (expired), falls
    back to default credentials automatically.
    """
    title = f"{ticker} - {segment.title} (中文)"

    # Use the same focus prompt as English — the curated source doc
    # already handles content selection; focus prompt just tells hosts
    # *how* to discuss.  Prepend Chinese language instruction.
    focus_prompt = (
        "重要：请全程使用中文（简体中文）进行讨论。\n\n"
        + _load_focus_prompt(ticker)
    )

    # Try daily-reads credentials first, fall back to default
    for use_daily_reads in (True, False):
        ctx = _swap_credentials(_DAILY_READS_CREDS) if use_daily_reads else contextlib.nullcontext()
        label = "daily-reads" if use_daily_reads else "default"
        try:
            with ctx:
                log.info("Trying %s credentials for Chinese video", label)
                notebook_id = _create_notebook_and_add_source(title, source_file)
                _generate_video_via_sdk(notebook_id, "zh_Hans", focus_prompt)
                status = _poll_video_status()

                if status != "completed":
                    log.error("Chinese video ended with status: %s", status)
                    return None

                output_path = work_dir / f"{ticker}_{segment.segment_id}_zh_raw.mp4"
                return _download_video(output_path)
        except Exception:
            if use_daily_reads:
                log.warning("daily-reads credentials failed, trying default")
                continue
            log.exception("Chinese CLI pipeline failed with default credentials")
            return None
    return None


def generate_curated_video(session) -> Path | None:
    """Generate a Chinese video from the session's curated document.

    Unlike generate_segment_video_chinese, this uses the full curated
    document as source (no 1/3 trimming) and derives title from the
    selected angle name.
    """
    ticker = session.ticker.upper()
    work_dir = Path(tempfile.mkdtemp(prefix=f"nlm-curated-{ticker}-"))

    # Get angle name for title
    angle_name = "Curated Analysis"
    if session.selected_angle_index >= 0 and session.video_angles:
        angle = session.video_angles[session.selected_angle_index]
        angle_name = angle.get("angle_name", angle_name)

    source_file = work_dir / f"{ticker}_curated_source.md"
    source_file.write_text(
        f"# {ticker} - {angle_name}\n\n{session.curated_document}",
        encoding="utf-8",
    )
    log.info("Wrote curated source (%d chars) to %s",
             len(session.curated_document), source_file)

    title = f"{ticker} - {angle_name} (中文)"
    focus_prompt = (
        "重要：请全程使用中文（简体中文）进行讨论。\n\n"
        + _load_focus_prompt(ticker)
    )

    # Try daily-reads credentials first, fall back to default
    for use_daily_reads in (True, False):
        ctx = _swap_credentials(_DAILY_READS_CREDS) if use_daily_reads else contextlib.nullcontext()
        label = "daily-reads" if use_daily_reads else "default"
        try:
            with ctx:
                log.info("Trying %s credentials for curated video", label)
                notebook_id = _create_notebook_and_add_source(title, source_file)
                _generate_video_via_sdk(notebook_id, "zh_Hans", focus_prompt)
                status = _poll_video_status()

                if status != "completed":
                    log.error("Curated video ended with status: %s", status)
                    return None

                output_path = work_dir / f"{ticker}_curated_zh_raw.mp4"
                video_path = _download_video(output_path)
                if not video_path:
                    return None

                # Post-process: trim + logo
                try:
                    return _ffmpeg_trim_and_logo(video_path, work_dir)
                except Exception:
                    log.exception("Curated video post-processing failed")
                    return video_path
        except Exception:
            if use_daily_reads:
                log.warning("daily-reads credentials failed for curated video, trying default")
                continue
            log.exception("Curated video pipeline failed with default credentials")
            return None
    return None


def generate_curated_video_english(session) -> Path | None:
    """Generate an English video from the session's curated document.

    Same curated document as Chinese, but with:
    - language="en" for NotebookLM
    - English focus prompt prefix
    - Post-processing: trim + transcribe + translate + bilingual subtitles + logo
    """
    ticker = session.ticker.upper()
    work_dir = Path(tempfile.mkdtemp(prefix=f"nlm-curated-en-{ticker}-"))

    # Get angle name for title
    angle_name = "Curated Analysis"
    if session.selected_angle_index >= 0 and session.video_angles:
        angle = session.video_angles[session.selected_angle_index]
        angle_name = angle.get("angle_name", angle_name)

    source_file = work_dir / f"{ticker}_curated_en_source.md"
    source_file.write_text(
        f"# {ticker} - {angle_name}\n\n{session.curated_document}",
        encoding="utf-8",
    )
    log.info("Wrote English curated source (%d chars) to %s",
             len(session.curated_document), source_file)

    title = f"{ticker} - {angle_name} (English)"
    focus_prompt = (
        "Important: Please conduct the entire discussion in English.\n\n"
        + _load_focus_prompt(ticker)
    )

    # Try daily-reads credentials first, fall back to default
    for use_daily_reads in (True, False):
        ctx = _swap_credentials(_DAILY_READS_CREDS) if use_daily_reads else contextlib.nullcontext()
        label = "daily-reads" if use_daily_reads else "default"
        try:
            with ctx:
                log.info("Trying %s credentials for English curated video", label)
                notebook_id = _create_notebook_and_add_source(title, source_file)
                _generate_video_via_sdk(notebook_id, "en", focus_prompt)
                status = _poll_video_status()

                if status != "completed":
                    log.error("English curated video ended with status: %s", status)
                    return None

                output_path = work_dir / f"{ticker}_curated_en_raw.mp4"
                video_path = _download_video(output_path)
                if not video_path:
                    return None

                # Post-process: trim + transcribe + translate + bilingual subtitles + logo
                try:
                    return _postprocess_english_video(video_path, work_dir)
                except Exception:
                    log.exception("English curated video post-processing failed")
                    return video_path
        except Exception:
            if use_daily_reads:
                log.warning("daily-reads credentials failed for English curated video, trying default")
                continue
            log.exception("English curated video pipeline failed with default credentials")
            return None
    return None


def _postprocess_english_video(video_path: Path, work_dir: Path) -> Path:
    """Trim + transcribe + translate + bilingual subtitles + logo.

    Reuses functions from ~/clawd/skills/xiaohongshu-publish/process_notebooklm.py.
    """
    from process_notebooklm import (
        extract_audio,
        transcribe_with_groq,
        translate_segments,
        generate_srt,
        embed_subtitles_with_logo,
    )

    # 1. Trim 2.5s from end
    trimmed_path = work_dir / f"{video_path.stem}_trimmed.mp4"
    try:
        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
        ]
        duration = float(subprocess.check_output(probe_cmd, text=True).strip())
        trim_cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-t", str(duration - 2.5),
            "-c", "copy", str(trimmed_path),
        ]
        subprocess.run(trim_cmd, check=True, capture_output=True)
        log.info("Trimmed 2.5s → %s", trimmed_path)
    except Exception:
        log.warning("Trim failed, using original video")
        trimmed_path = video_path

    # 2. Extract audio
    audio_path = work_dir / "audio.mp3"
    extract_audio(str(trimmed_path), str(audio_path))
    log.info("Extracted audio → %s", audio_path)

    # 3. Transcribe with Groq (English)
    segments = transcribe_with_groq(str(audio_path))
    log.info("Transcribed %d segments", len(segments))

    # 4. Translate segments (add Chinese translations)
    translate_segments(segments)
    log.info("Translated segments to Chinese")

    # 5. Generate bilingual SRT
    srt_path = work_dir / "subtitles.srt"
    generate_srt(segments, str(srt_path), bilingual=True)
    log.info("Generated bilingual SRT → %s", srt_path)

    # 6. Embed subtitles + logo
    output_path = work_dir / f"{video_path.stem}_en_final.mp4"
    logo = str(_LOGO_PATH) if _LOGO_PATH.exists() else None
    embed_subtitles_with_logo(str(trimmed_path), str(output_path), str(srt_path), logo)
    log.info("Embedded subtitles + logo → %s", output_path)

    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    return trimmed_path


def _trim_to_paragraphs(text: str, target_len: int) -> str:
    """Trim text to approximately target_len characters at a paragraph boundary."""
    if len(text) <= target_len:
        return text
    paragraphs = text.split("\n\n")
    result = []
    total = 0
    for p in paragraphs:
        if total + len(p) > target_len and result:
            break
        result.append(p)
        total += len(p) + 2  # +2 for \n\n
    return "\n\n".join(result) if result else text[:target_len]


def _ffmpeg_trim_and_logo(video_path: Path, work_dir: Path) -> Path:
    """Trim 2.5s from end + overlay 100Baggers logo (Chinese videos).

    Uses process_notebooklm.process_video_simple() (same as article-to-video
    pipeline's --logo-only mode).  Falls back to direct ffmpeg if unavailable.
    """
    # Primary: use process_video_simple (same as article-to-video pipeline)
    try:
        from process_notebooklm import process_video_simple
        result = process_video_simple(str(video_path), str(work_dir))
        processed = result.get("video")
        if processed and Path(processed).exists():
            return Path(processed)
    except (ImportError, Exception):
        log.info("process_video_simple not available, using direct ffmpeg")

    # Fallback: direct ffmpeg
    output_path = work_dir / f"{video_path.stem}_zh_processed.mp4"
    logo = str(_LOGO_PATH) if _LOGO_PATH.exists() else None

    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
    ]
    try:
        duration = float(subprocess.check_output(probe_cmd, text=True).strip())
    except Exception:
        log.warning("Could not probe video duration, skipping trim")
        duration = None

    cmd = ["ffmpeg", "-y", "-i", str(video_path)]

    if logo:
        cmd += ["-i", logo]

    filter_parts = []
    if logo:
        filter_parts.append("[1:v]scale=-1:40[wm]")
        filter_parts.append("[0:v][wm]overlay=W-w-15:H-h-15[outv]")
        map_video = "[outv]"
    else:
        map_video = "0:v"

    if filter_parts:
        cmd += ["-filter_complex", ";".join(filter_parts)]
        cmd += ["-map", map_video, "-map", "0:a"]
    else:
        cmd += ["-c", "copy"]

    if duration and duration > 5:
        cmd += ["-t", str(duration - 2.5)]

    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
    cmd += ["-c:a", "aac", "-b:a", "128k"]
    cmd.append(str(output_path))

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        log.info("Processed Chinese video: %s", output_path)
        return output_path
    except subprocess.CalledProcessError as e:
        log.error("ffmpeg failed: %s", e.stderr.decode() if e.stderr else str(e))
        return video_path
