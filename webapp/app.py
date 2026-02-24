#!/usr/bin/env python3
"""
Content Review + Publishing Web App.

A Flask app for reviewing, editing, and publishing segmented report content.
Run with:  python webapp/app.py
"""

from __future__ import annotations

import logging
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, send_from_directory

from engine.config import AVAILABLE_TICKERS
from engine.config import find_html_report, find_english_html_report
from engine.config import find_markdown_report, find_english_markdown
from engine.markdown_parser import MarkdownReportParser
from engine.report_parser import HTMLReportParser
from engine.segment_splitter import SegmentSplitter
from engine.segment_generator import generate_all_segments
from webapp.state import SessionState

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "100baggers-review-local-only"

PLATFORMS = ["xueqiu", "xiaohongshu", "twitter", "youtube"]

_SCREENSHOT_DIR = Path(__file__).resolve().parent / "static" / "screenshots"

_PLATFORM_LANGUAGE = {
    "xueqiu": "zh",
    "xiaohongshu": "zh",
    "twitter": "en",
    "youtube": "en",
}


# ── Helpers ──────────────────────────────────────────────────────────

def _load_report(ticker: str, language: str = "zh"):
    """Parse a report for the given ticker.

    Prefers HTML (which reflects manual edits) over raw Markdown.
    Uses language to pick Chinese or English report.
    """
    html_parser = HTMLReportParser()

    if language == "en":
        html_path = find_english_html_report(ticker)
        if html_path:
            return html_parser.parse(html_path)
        # Fallback: English markdown
        md_path = find_english_markdown(ticker)
        if md_path:
            return MarkdownReportParser().parse(md_path)

    # Chinese (default) — HTML first
    html_path = find_html_report(ticker)
    if html_path:
        return html_parser.parse(html_path)
    # Fallback: Chinese markdown
    md_path = find_markdown_report(ticker)
    if md_path:
        return MarkdownReportParser().parse(md_path)
    return None


def _get_session_or_404(session_id: str) -> SessionState:
    session = SessionState.load(session_id)
    if session is None:
        abort(404, description="Session not found")
    return session


def _format_platform_content(content, platform: str) -> str:
    """Format platform content for display in the editor."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "error" in content:
            return f"[Generation Error] {content['error']}"
        if platform == "xiaohongshu":
            parts = []
            if "title" in content:
                parts.append(f"# {content['title']}\n")
            for i, slide in enumerate(content.get("slides", []), 1):
                parts.append(f"## Slide {i}\n{slide}\n")
            if "caption" in content:
                parts.append(f"---\n**Caption:**\n{content['caption']}")
            return "\n".join(parts)
        if platform == "youtube":
            parts = []
            if "title" in content:
                parts.append(f"# {content['title']}\n")
            if "description" in content:
                parts.append(f"**Description:**\n{content['description']}\n")
            if "script" in content:
                parts.append(f"---\n**Script:**\n{content['script']}")
            if "tags" in content:
                parts.append(f"\n**Tags:** {', '.join(content['tags'])}")
            return "\n".join(parts)
        # Generic dict
        return "\n".join(f"**{k}:** {v}" for k, v in content.items())
    if isinstance(content, list):
        return "\n\n".join(str(item) for item in content)
    return str(content)


# ── Routes: Pages ────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Dashboard: ticker grid + active sessions."""
    sessions = SessionState.list_all()
    return render_template(
        "dashboard.html",
        tickers=AVAILABLE_TICKERS,
        platforms=PLATFORMS,
        sessions=sessions,
    )


@app.route("/session/new", methods=["POST"])
def create_session():
    """Create a new review session: parse → split → generate → redirect."""
    ticker = request.form.get("ticker", "").strip().lower()
    platform = request.form.get("platform", "").strip().lower()

    if ticker not in AVAILABLE_TICKERS:
        abort(400, description=f"Unknown ticker: {ticker}")
    if platform not in PLATFORMS:
        abort(400, description=f"Unknown platform: {platform}")

    # Create session
    session = SessionState.create(ticker, platform)
    session.overall_status = "splitting"
    session.save()

    # Parse report (HTML preferred, language-aware)
    lang = _PLATFORM_LANGUAGE.get(platform, "zh")
    report = _load_report(ticker, language=lang)
    if report is None:
        session.overall_status = "failed"
        session.save()
        abort(404, description=f"No report found for {ticker}")

    # Split into segments
    splitter = SegmentSplitter(platform)
    segments = splitter.split(report)
    session.segments = segments
    session.overall_status = "generating"
    session.save()

    # Generate content for each segment (synchronous for now)
    generate_all_segments(segments, report, platform)

    # Capture screenshots from rendered report (language-aware)
    try:
        from webapp.screenshot import capture_report_screenshots_sync
        lang = _PLATFORM_LANGUAGE.get(platform, "zh")
        for seg in segments:
            screenshots = capture_report_screenshots_sync(
                ticker=ticker,
                segment_theme=seg.theme,
                session_id=session.session_id,
                segment_id=seg.segment_id,
                max_screenshots=3,
                language=lang,
            )
            seg.screenshots = screenshots
    except Exception:
        log.exception("Screenshot capture failed — continuing without screenshots")

    session.overall_status = "reviewing"
    session.save()

    return redirect(url_for("view_session", session_id=session.session_id))


@app.route("/session/<session_id>")
def view_session(session_id: str):
    """Show all segments for a session."""
    session = _get_session_or_404(session_id)
    # Pre-format content for display
    formatted = {}
    for seg in session.segments:
        content = seg.platform_content.get(session.platform, "")
        formatted[seg.segment_id] = _format_platform_content(content, session.platform)
    return render_template(
        "session.html",
        session=session,
        formatted=formatted,
    )


@app.route("/session/<session_id>/segment/<segment_id>")
def edit_segment(session_id: str, segment_id: str):
    """Full-page segment editor."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404, description="Segment not found")
    content = segment.platform_content.get(session.platform, "")
    formatted = _format_platform_content(content, session.platform)
    return render_template(
        "segment_edit.html",
        session=session,
        segment=segment,
        formatted=formatted,
    )


# ── Routes: API (HTMX) ─────────────────────────────────────────────

@app.route("/api/session/<session_id>/segment/<segment_id>/save", methods=["POST"])
def save_segment(session_id: str, segment_id: str):
    """Save edited content for a segment."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)

    content = request.form.get("content", "")
    platform = session.platform

    # Store edited content — for structured platforms, store as string override
    segment.platform_content[platform] = content
    session.save()

    return render_template("_segment_card.html", session=session, segment=segment,
                           formatted=content)


@app.route("/api/session/<session_id>/segment/<segment_id>/regenerate", methods=["POST"])
def regenerate_segment(session_id: str, segment_id: str):
    """Re-run content generation for a segment."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)

    lang = _PLATFORM_LANGUAGE.get(session.platform, "zh")
    report = _load_report(session.ticker, language=lang)
    if report is None:
        return jsonify({"error": "Report not found"}), 404

    from engine.segment_generator import generate_segment_content
    try:
        content = generate_segment_content(segment, report, session.platform)
        segment.platform_content[session.platform] = content
        segment.status = "draft"
        session.save()
    except Exception as e:
        log.exception("Regeneration failed")
        return jsonify({"error": str(e)}), 500

    formatted = _format_platform_content(
        segment.platform_content.get(session.platform, ""), session.platform
    )
    return render_template("_segment_card.html", session=session, segment=segment,
                           formatted=formatted)


@app.route("/api/session/<session_id>/segment/<segment_id>/approve", methods=["POST"])
def approve_segment(session_id: str, segment_id: str):
    """Toggle segment approval status."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)

    # Toggle: draft <-> approved
    segment.status = "approved" if segment.status != "approved" else "draft"
    if session.all_approved():
        session.overall_status = "approved"
    else:
        session.overall_status = "reviewing"
    session.save()

    formatted = _format_platform_content(
        segment.platform_content.get(session.platform, ""), session.platform
    )
    return render_template("_segment_card.html", session=session, segment=segment,
                           formatted=formatted)


@app.route("/api/session/<session_id>/segment/<segment_id>/video/generate", methods=["POST"])
def generate_video(session_id: str, segment_id: str):
    """Trigger NotebookLM video generation for a segment."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)

    if segment.video_status == "generating":
        return jsonify({"status": "already_generating"}), 409

    segment.video_status = "generating"
    session.save()

    # Run in background thread
    def _bg_generate():
        try:
            from webapp.notebooklm import generate_segment_video
            video_path = generate_segment_video(session, segment)
            segment.video_path = str(video_path) if video_path else ""
            segment.video_status = "ready" if video_path else "failed"
        except Exception:
            log.exception("Video generation failed for %s", segment.segment_id)
            segment.video_status = "failed"
        session.save()

    threading.Thread(target=_bg_generate, daemon=True).start()
    return jsonify({"status": "generating", "segment_id": segment_id})


@app.route("/api/session/<session_id>/segment/<segment_id>/video/status")
def video_status(session_id: str, segment_id: str):
    """Poll video generation status."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)
    return jsonify({
        "status": segment.video_status,
        "video_path": segment.video_path,
    })


@app.route("/api/session/<session_id>/publish", methods=["POST"])
def publish_session(session_id: str):
    """Publish all approved segments."""
    session = _get_session_or_404(session_id)
    dry_run = request.form.get("dry_run", "true").lower() == "true"

    approved = [s for s in session.segments if s.status == "approved"]
    if not approved:
        return jsonify({"error": "No approved segments"}), 400

    results = []
    for seg in approved:
        content = seg.platform_content.get(session.platform, "")
        if not content:
            results.append({"segment_id": seg.segment_id, "ok": False, "error": "No content"})
            continue

        try:
            ok = _publish_segment(
                session.platform, content, session.ticker, dry_run,
                screenshots=seg.screenshots,
            )
            seg.status = "published" if ok else "approved"
            results.append({"segment_id": seg.segment_id, "ok": ok})
            # Archive on successful real publish (not dry-run)
            if ok and not dry_run:
                try:
                    _archive_segment(session.platform, session.ticker, seg, session_id)
                except Exception:
                    log.exception("Archive failed for %s (publish still OK)", seg.segment_id)
        except Exception as e:
            log.exception("Publish failed for %s", seg.segment_id)
            results.append({"segment_id": seg.segment_id, "ok": False, "error": str(e)})

    if all(r["ok"] for r in results):
        session.overall_status = "published"
    session.save()

    return jsonify({"results": results, "dry_run": dry_run})


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename: str):
    """Serve screenshot files from the static screenshots directory."""
    return send_from_directory(str(_SCREENSHOT_DIR), filename)


@app.route("/api/session/<session_id>/delete", methods=["POST"])
def delete_session(session_id: str):
    """Delete a session."""
    session = _get_session_or_404(session_id)
    session.delete()
    return redirect(url_for("dashboard"))


def _archive_segment(
    platform: str, ticker: str, segment: object, session_id: str,
) -> Path | None:
    """Save published segment content + screenshots to platforms/{platform}/archive/."""
    archive_dir = _PROJECT_ROOT / "platforms" / platform / "archive" / ticker.lower()
    archive_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H%M")
    slug = f"{timestamp}-{segment.theme}"

    # Save content
    content = segment.platform_content.get(platform, "")
    text = content if isinstance(content, str) else str(content)
    header = (
        f"---\n"
        f"ticker: {ticker.upper()}\n"
        f"platform: {platform}\n"
        f"theme: {segment.theme}\n"
        f"segment: {segment.segment_id}\n"
        f"session: {session_id}\n"
        f"published_at: {now.isoformat(timespec='seconds')}\n"
        f"---\n\n"
    )
    content_path = archive_dir / f"{slug}.md"
    content_path.write_text(header + text, encoding="utf-8")
    log.info("Archived segment to %s", content_path)

    # Copy screenshots alongside
    if segment.screenshots:
        img_dir = archive_dir / f"{slug}_images"
        img_dir.mkdir(exist_ok=True)
        for url in segment.screenshots:
            src = _SCREENSHOT_DIR.parent / url.lstrip("/")
            if src.exists():
                shutil.copy2(src, img_dir / src.name)

    return content_path


def _publish_segment(
    platform: str, content, ticker: str, dry_run: bool,
    screenshots: list[str] | None = None,
) -> bool:
    """Dispatch publishing to the appropriate platform publisher."""
    import importlib
    pub_mod = importlib.import_module(f"platforms.{platform}.publish")

    if platform == "xueqiu":
        text = content if isinstance(content, str) else str(content)
        image_paths = None
        if screenshots:
            # Convert relative URLs to absolute file paths
            image_paths = [
                _SCREENSHOT_DIR.parent / url.lstrip("/")
                for url in screenshots
            ]
            image_paths = [p for p in image_paths if p.exists()]
            if not image_paths:
                image_paths = None
        return pub_mod.publish(content=text, ticker=ticker, dry_run=dry_run, images=image_paths)
    elif platform == "twitter":
        text = content if isinstance(content, str) else str(content)
        return pub_mod.publish(content=text, ticker=ticker, dry_run=dry_run)
    elif platform == "xiaohongshu":
        # Write content to a temp dir for the publisher
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix=f"xhs-{ticker}-"))
        content_path = tmp / f"{ticker}_xiaohongshu.md"
        text = content if isinstance(content, str) else str(content)
        content_path.write_text(text, encoding="utf-8")
        return pub_mod.publish(content_dir=tmp, ticker=ticker, dry_run=dry_run)
    elif platform == "youtube":
        # YouTube needs video_path — only publish if video is ready
        if isinstance(content, dict) and "title" in content:
            return pub_mod.publish(
                video_path=Path(content.get("video_path", "")),
                title=content["title"],
                description=content.get("description", ""),
                tags=content.get("tags", []),
                dry_run=dry_run,
            )
        return False
    return False


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
