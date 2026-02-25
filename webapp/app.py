#!/usr/bin/env python3
"""
Content Review + Publishing Web App.

A Flask app for reviewing, editing, and publishing segmented report content.
Run with:  python webapp/app.py
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, send_from_directory

from engine.config import AVAILABLE_TICKERS, get_company_name
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
_VIDEOS_DIR = Path(__file__).resolve().parent / "static" / "videos"
_SLIDES_DIR = Path(__file__).resolve().parent / "static" / "slides"

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


def _extract_slides_from_content(content) -> tuple[list[str], str, str]:
    """Extract slide texts, title, and caption from XHS platform content.

    Returns (slides, title, caption).
    """
    if isinstance(content, dict):
        return (
            content.get("slides", []),
            content.get("title", ""),
            content.get("caption", ""),
        )
    # Parse from formatted string (## Slide N format)
    import re
    slides = []
    title = ""
    if isinstance(content, str):
        title_match = re.search(r"^# (.+)", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        for m in re.finditer(r"## Slide \d+\n(.+?)(?=\n## Slide|\n---|\Z)", content, re.DOTALL):
            slides.append(m.group(1).strip())
    return slides, title, ""


def _render_segment_slides(session, segment, report=None):
    """Render slide images for a single XHS segment."""
    from platforms.xiaohongshu.render_slides import render_all_slides

    content = segment.platform_content.get("xiaohongshu", "")
    slides, title, _ = _extract_slides_from_content(content)
    if not slides:
        return

    company_name = ""
    if report and hasattr(report, "metadata"):
        company_name = report.metadata.company_name or ""

    output_dir = _SLIDES_DIR / session.session_id / segment.segment_id
    jpg_paths = render_all_slides(
        slides=slides,
        ticker=session.ticker,
        output_dir=output_dir,
        company_name=company_name,
        title=title,
    )

    # Store as URL paths for the template
    segment.slide_images = [
        f"/static/slides/{session.session_id}/{segment.segment_id}/{p.name}"
        for p in jpg_paths
    ]


def _render_xhs_slides(session, segments, report):
    """Render slide images for all segments in an XHS session."""
    for seg in segments:
        try:
            _render_segment_slides(session, seg, report)
        except Exception:
            log.exception("Slide render failed for segment %s", seg.segment_id)


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

    # Render slide images for XHS sessions
    if platform == "xiaohongshu":
        try:
            _render_xhs_slides(session, segments, report)
        except Exception:
            log.exception("Slide rendering failed — continuing without slides")

    session.overall_status = "reviewing"
    session.save()

    # Auto-trigger video angle recommendation in background
    _launch_angle_recommendation(session)

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


@app.route("/api/session/<session_id>/segment/<segment_id>/video-zh/generate", methods=["POST"])
def generate_video_zh(session_id: str, segment_id: str):
    """Trigger Chinese NotebookLM video generation for an XHS segment."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)

    if segment.video_zh_status == "generating":
        return jsonify({"status": "already_generating"}), 409

    segment.video_zh_status = "generating"
    session.save()

    def _bg_generate_zh():
        try:
            from webapp.notebooklm import generate_segment_video_chinese
            video_path = generate_segment_video_chinese(session, segment)
            if video_path:
                # Copy to static dir for serving
                dest_dir = _VIDEOS_DIR / session_id / segment_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / video_path.name
                shutil.copy2(video_path, dest)
                segment.video_zh_path = f"/static/videos/{session_id}/{segment_id}/{video_path.name}"
                segment.video_zh_status = "ready"
            else:
                segment.video_zh_status = "failed"
        except Exception:
            log.exception("Chinese video generation failed for %s", segment.segment_id)
            segment.video_zh_status = "failed"
        session.save()

    threading.Thread(target=_bg_generate_zh, daemon=True).start()
    return jsonify({"status": "generating", "segment_id": segment_id})


@app.route("/api/session/<session_id>/segment/<segment_id>/video-zh/status")
def video_zh_status(session_id: str, segment_id: str):
    """Poll Chinese video generation status."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)
    return jsonify({
        "status": segment.video_zh_status,
        "video_path": segment.video_zh_path,
    })


@app.route("/api/session/<session_id>/segment/<segment_id>/slides/regenerate", methods=["POST"])
def regenerate_slides(session_id: str, segment_id: str):
    """Re-render slide images after text edits."""
    session = _get_session_or_404(session_id)
    segment = session.segment_by_id(segment_id)
    if segment is None:
        abort(404)

    lang = _PLATFORM_LANGUAGE.get(session.platform, "zh")
    report = _load_report(session.ticker, language=lang)

    try:
        _render_segment_slides(session, segment, report)
        session.save()
    except Exception as e:
        log.exception("Slide re-render failed")
        return jsonify({"error": str(e)}), 500

    formatted = _format_platform_content(
        segment.platform_content.get(session.platform, ""), session.platform
    )
    return render_template("_segment_card.html", session=session, segment=segment,
                           formatted=formatted)


@app.route("/api/session/<session_id>/publish", methods=["POST"])
def publish_session(session_id: str):
    """Publish all approved segments."""
    session = _get_session_or_404(session_id)
    dry_run = request.form.get("dry_run", "true").lower() == "true"

    publish_mode = request.form.get("publish_mode", "")  # "slides" or "video" for XHS

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
                publish_mode=publish_mode,
                segment=seg,
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


# ── Video Curation Pipeline ──────────────────────────────────────────

def _launch_angle_recommendation(session):
    """Launch background thread to recommend video angles for a session."""
    session.video_angles_status = "generating"
    session.save()

    def _bg_recommend():
        try:
            from webapp.video_curation import recommend_angles
            ticker = session.ticker
            company_name = get_company_name(ticker)
            lang = _PLATFORM_LANGUAGE.get(session.platform, "zh")
            report = _load_report(ticker, language=lang)
            if report is None:
                log.error("No report found for angle recommendation: %s", ticker)
                session.video_angles_status = "failed"
                session.save()
                return
            # Build full report text from chapters
            report_text = "\n\n".join(
                f"# {ch.title}\n\n{ch.content_markdown}" for ch in report.chapters
            )
            angles = recommend_angles(ticker, company_name, report_text)
            session.video_angles = angles
            session.video_angles_status = "ready"
        except Exception:
            log.exception("Angle recommendation failed for %s", session.ticker)
            session.video_angles_status = "failed"
        session.save()

    threading.Thread(target=_bg_recommend, daemon=True).start()


@app.route("/api/session/<session_id>/angles/status")
def angles_status(session_id: str):
    """Poll angle recommendation status."""
    session = _get_session_or_404(session_id)
    return jsonify({
        "status": session.video_angles_status,
        "angle_count": len(session.video_angles),
    })


@app.route("/api/session/<session_id>/angles/recommend", methods=["POST"])
def angles_recommend(session_id: str):
    """Manually trigger (or retry) angle recommendation."""
    session = _get_session_or_404(session_id)
    if session.video_angles_status == "generating":
        return jsonify({"status": "already_generating"}), 409
    _launch_angle_recommendation(session)
    return jsonify({"status": "generating"})


@app.route("/api/session/<session_id>/angles/select", methods=["POST"])
def angles_select(session_id: str):
    """Select an angle and trigger document curation."""
    session = _get_session_or_404(session_id)
    angle_index = int(request.form.get("angle_index", -1))
    if angle_index < 0 or angle_index >= len(session.video_angles):
        return jsonify({"error": "Invalid angle index"}), 400

    session.selected_angle_index = angle_index
    session.curation_status = "generating"
    session.save()

    # Launch curation in background
    def _bg_curate():
        try:
            from webapp.video_curation import curate_document
            ticker = session.ticker
            company_name = get_company_name(ticker)
            lang = _PLATFORM_LANGUAGE.get(session.platform, "zh")
            report = _load_report(ticker, language=lang)
            if report is None:
                log.error("No report found for curation: %s", ticker)
                session.curation_status = "failed"
                session.save()
                return
            report_text = "\n\n".join(
                f"# {ch.title}\n\n{ch.content_markdown}" for ch in report.chapters
            )
            selected_angle = session.video_angles[angle_index]
            curated = curate_document(ticker, company_name, report_text, selected_angle)
            session.curated_document = curated
            session.curation_status = "ready"
        except Exception:
            log.exception("Document curation failed for %s", session.ticker)
            session.curation_status = "failed"
        session.save()

    threading.Thread(target=_bg_curate, daemon=True).start()
    return jsonify({"status": "generating"})


@app.route("/api/session/<session_id>/curation/status")
def curation_status(session_id: str):
    """Poll document curation status."""
    session = _get_session_or_404(session_id)
    return jsonify({
        "status": session.curation_status,
        "document_length": len(session.curated_document),
    })


@app.route("/api/session/<session_id>/curated-video/generate", methods=["POST"])
def curated_video_generate(session_id: str):
    """Generate video from curated document. Supports language: zh, en, both."""
    session = _get_session_or_404(session_id)
    language = request.form.get("language", "zh")  # zh|en|both

    if language in ("zh", "both") and session.curated_video_status == "generating":
        return jsonify({"status": "already_generating"}), 409
    if language == "en" and session.curated_video_en_status == "generating":
        return jsonify({"status": "already_generating"}), 409
    if not session.curated_document:
        return jsonify({"error": "No curated document available"}), 400

    if language in ("zh", "both"):
        session.curated_video_status = "generating"
    if language in ("en", "both"):
        session.curated_video_en_status = "generating"
    session.save()

    def _bg_generate_curated():
        dest_dir = _VIDEOS_DIR / session_id / "curated"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # ── Chinese video ──
        if language in ("zh", "both"):
            try:
                from webapp.notebooklm import generate_curated_video
                video_path = generate_curated_video(session)
                if video_path:
                    dest = dest_dir / video_path.name
                    shutil.copy2(video_path, dest)
                    session.curated_video_path = f"/static/videos/{session_id}/curated/{video_path.name}"
                    session.curated_video_status = "ready"
                    if not session.curated_xhs_post:
                        session.curated_xhs_post = _generate_xhs_post_content(session)
                else:
                    session.curated_video_status = "failed"
            except Exception:
                log.exception("Curated video generation failed for %s", session.ticker)
                session.curated_video_status = "failed"
            session.save()

        # ── English video ──
        if language in ("en", "both"):
            session.curated_video_en_status = "generating"
            session.save()
            try:
                from webapp.notebooklm import generate_curated_video_english
                video_path = generate_curated_video_english(session)
                if video_path:
                    dest = dest_dir / video_path.name
                    shutil.copy2(video_path, dest)
                    session.curated_video_en_path = f"/static/videos/{session_id}/curated/{video_path.name}"
                    session.curated_video_en_status = "ready"
                else:
                    session.curated_video_en_status = "failed"
            except Exception:
                log.exception("English curated video generation failed for %s", session.ticker)
                session.curated_video_en_status = "failed"
            session.save()

    threading.Thread(target=_bg_generate_curated, daemon=True).start()
    return jsonify({"status": "generating", "language": language})


@app.route("/api/session/<session_id>/curated-video/status")
def curated_video_status(session_id: str):
    """Poll curated video generation status (Chinese + English)."""
    session = _get_session_or_404(session_id)
    return jsonify({
        "status": session.curated_video_status,
        "video_path": session.curated_video_path,
        "en_status": session.curated_video_en_status,
        "en_video_path": session.curated_video_en_path,
    })


def _generate_xhs_post_content(session) -> str:
    """Generate XHS post markdown from the selected angle."""
    ticker = session.ticker.upper()
    company_name = get_company_name(ticker)

    angle_name = ""
    core_thesis = ""
    if session.selected_angle_index >= 0 and session.video_angles:
        angle = session.video_angles[session.selected_angle_index]
        angle_name = angle.get("angle_name", "")
        core_thesis = angle.get("core_thesis", "")

    title = f"{ticker}: {angle_name}" if angle_name else f"{ticker} 深度研究"
    # XHS title limit: 20 chars
    if len(title) > 20:
        title = title[:20]

    body = core_thesis if core_thesis else f"{company_name}深度研究报告解读"
    tags = f"#深度研究 #{ticker} #{company_name} #投资分析 #美股"
    disclaimer = "⚠️ 信息整理，不构成投资建议"

    return f"{title}\n\n{body}\n\n{tags}\n\n{disclaimer}"


@app.route("/api/session/<session_id>/curated-video/save-post", methods=["POST"])
def curated_video_save_post(session_id: str):
    """Save edited XHS post content."""
    session = _get_session_or_404(session_id)
    session.curated_xhs_post = request.form.get("xhs_post", "")
    session.save()
    return jsonify({"status": "saved"})


@app.route("/api/session/<session_id>/curated-video/publish", methods=["POST"])
def curated_video_publish(session_id: str):
    """Publish curated video to XHS using the existing xhs_publisher."""
    session = _get_session_or_404(session_id)

    if session.curated_publish_status == "publishing":
        return jsonify({"status": "already_publishing"}), 409
    if not session.curated_video_path:
        return jsonify({"error": "No video available"}), 400

    session.curated_publish_status = "publishing"
    session.save()

    def _bg_publish():
        try:
            ticker = session.ticker.lower()
            static_dir = Path(__file__).resolve().parent / "static"

            # 1. Video file
            video_file = static_dir / session.curated_video_path.lstrip("/").replace("static/", "", 1)
            if not video_file.exists():
                log.error("Video file not found: %s", video_file)
                session.curated_publish_status = "failed"
                session.save()
                return

            # 2. Cover image (pre-generated)
            cover_file = static_dir / "covers" / f"{ticker}_cover.jpg"
            if not cover_file.exists():
                # Generate cover on the fly
                from webapp.generate_cover import render_cover, get_cover_title
                title = get_cover_title(ticker)
                cover_file = render_cover(ticker, title)

            # 3. XHS post content
            if not session.curated_xhs_post:
                session.curated_xhs_post = _generate_xhs_post_content(session)
                session.save()

            tmp_dir = Path(tempfile.mkdtemp(prefix=f"xhs-curated-{ticker}-"))
            post_md = tmp_dir / "xhs_post.md"
            post_md.write_text(session.curated_xhs_post, encoding="utf-8")

            # 4. Call xhs_publisher.py via subprocess
            xhs_publisher = Path.home() / "clawd" / "skills" / "earnings-video" / "xhs_publisher.py"
            cmd = [
                sys.executable, str(xhs_publisher),
                str(video_file),
                str(cover_file),
                str(post_md),
            ]
            log.info("Publishing to XHS: %s", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                session.curated_publish_status = "published"
                log.info("XHS publish succeeded for %s", ticker)
            else:
                log.error("XHS publish failed: %s", result.stderr)
                session.curated_publish_status = "failed"
        except Exception:
            log.exception("XHS publish failed for %s", session.ticker)
            session.curated_publish_status = "failed"
        session.save()

    threading.Thread(target=_bg_publish, daemon=True).start()
    return jsonify({"status": "publishing"})


@app.route("/api/session/<session_id>/curated-video/publish-status")
def curated_video_publish_status(session_id: str):
    """Poll curated video publish status."""
    session = _get_session_or_404(session_id)
    return jsonify({"status": session.curated_publish_status})


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
    publish_mode: str = "",
    segment=None,
) -> bool:
    """Dispatch publishing to the appropriate platform publisher."""
    import importlib
    pub_mod = importlib.import_module(f"platforms.{platform}.publish")

    if platform == "xueqiu":
        text = content if isinstance(content, str) else str(content)
        image_paths = None
        if screenshots:
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
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix=f"xhs-{ticker}-"))
        text = content if isinstance(content, str) else str(content)
        static_root = Path(__file__).resolve().parent

        # Write text content
        content_path = tmp / f"{ticker}_xiaohongshu.md"
        content_path.write_text(text, encoding="utf-8")

        if publish_mode == "video" and segment and segment.video_zh_path:
            # Video mode: copy video + cover into content_dir
            video_src = static_root / segment.video_zh_path.lstrip("/")
            if not video_src.exists():
                video_src = Path(segment.video_zh_path)
            if video_src.exists():
                shutil.copy2(video_src, tmp / video_src.name)
            # Copy first slide as cover
            if segment.slide_images:
                cover_src = static_root / segment.slide_images[0].lstrip("/")
                if cover_src.exists():
                    shutil.copy2(cover_src, tmp / f"cover.jpg")
            return pub_mod.publish(content_dir=tmp, ticker=ticker, dry_run=dry_run, mode="video")

        elif publish_mode == "slides" and segment and segment.slide_images:
            # Slides mode: copy slide images as .png into content_dir
            for i, url in enumerate(segment.slide_images):
                src = static_root / url.lstrip("/")
                if src.exists():
                    shutil.copy2(src, tmp / f"slide_{i+1:02d}.png")
            return pub_mod.publish(content_dir=tmp, ticker=ticker, dry_run=dry_run, mode="slides")

        else:
            # Default: text-only publish
            return pub_mod.publish(content_dir=tmp, ticker=ticker, dry_run=dry_run)
    elif platform == "youtube":
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
