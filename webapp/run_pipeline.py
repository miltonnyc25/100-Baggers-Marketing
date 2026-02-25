#!/usr/bin/env python3
"""
Run the full curated-video pipeline for a ticker end-to-end.

Steps:
  1. Parse report
  2. Recommend video angles (Gemini)
  3. Auto-select best angle
  4. Curate document (Gemini)
  5. Generate video (NotebookLM)
  6. Generate XHS slides (Gemini + Playwright)
  7. Generate XHS post content
  8. Archive everything

Usage:
    python webapp/run_pipeline.py AMD
    python webapp/run_pipeline.py AMD --skip-video     # skip NotebookLM (for testing)
    python webapp/run_pipeline.py AMD --language en    # English only (zh|en|both, default: both)
    python webapp/run_pipeline.py AMD --dry-run        # skip publish step
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.config import AVAILABLE_TICKERS, get_company_name
from engine.config import find_html_report, find_markdown_report
from engine.markdown_parser import MarkdownReportParser
from engine.report_parser import HTMLReportParser
from webapp.video_curation import recommend_angles, curate_document

_COVERS_DIR = Path(__file__).resolve().parent / "static" / "covers"
_ARCHIVE_ROOT = _PROJECT_ROOT / "platforms" / "xiaohongshu" / "archive"


def _load_report(ticker: str):
    """Parse report (HTML preferred)."""
    html_path = find_html_report(ticker)
    if html_path:
        return HTMLReportParser().parse(html_path)
    md_path = find_markdown_report(ticker)
    if md_path:
        return MarkdownReportParser().parse(md_path)
    return None


def _build_report_text(report) -> str:
    """Concatenate all chapters into a single string."""
    return "\n\n".join(f"# {ch.title}\n\n{ch.content_markdown}" for ch in report.chapters)


def _generate_xhs_post(ticker: str, angle: dict) -> str:
    """Generate XHS post markdown from angle data."""
    company = get_company_name(ticker)
    name = angle.get("angle_name", "深度研究")
    thesis = angle.get("core_thesis", f"{company}深度研究报告解读")

    title = f"{ticker.upper()}: {name}"
    if len(title) > 20:
        title = title[:20]

    return (
        f"{title}\n\n"
        f"{thesis}\n\n"
        f"#深度研究 #{ticker.upper()} #{company} #投资分析 #美股\n\n"
        f"⚠️ 信息整理，不构成投资建议"
    )


def _archive_results(ticker: str, results: dict) -> Path:
    """Save all pipeline results to archive directory."""
    ticker_upper = ticker.upper()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    archive_dir = _ARCHIVE_ROOT / ticker.lower() / f"{timestamp}-curated-video"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 1. Strategy / angles
    angles_path = archive_dir / "angles.json"
    angles_path.write_text(
        json.dumps(results["angles"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  → angles.json ({len(results['angles'])} angles)")

    # 2. Selected angle
    sel_path = archive_dir / "selected_angle.json"
    sel_path.write_text(
        json.dumps(results["selected_angle"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  → selected_angle.json")

    # 3. Curated document
    if results.get("curated_document"):
        doc_path = archive_dir / "curated_document.md"
        doc_path.write_text(results["curated_document"], encoding="utf-8")
        print(f"  → curated_document.md ({len(results['curated_document'])} chars)")

    # 4. XHS post
    if results.get("xhs_post"):
        post_path = archive_dir / "xhs_post.md"
        post_path.write_text(results["xhs_post"], encoding="utf-8")
        print(f"  → xhs_post.md")

    # 5. Cover image (copy from static)
    cover_src = _COVERS_DIR / f"{ticker.lower()}_cover.jpg"
    if cover_src.exists():
        cover_dst = archive_dir / "cover.jpg"
        shutil.copy2(cover_src, cover_dst)
        print(f"  → cover.jpg (from existing covers)")

    # 6. Chinese video (copy if exists)
    if results.get("video_path"):
        video_src = Path(results["video_path"])
        if video_src.exists():
            video_dst = archive_dir / f"{ticker_upper}_curated_video_zh.mp4"
            shutil.copy2(video_src, video_dst)
            size_mb = video_dst.stat().st_size / (1024 * 1024)
            print(f"  → {video_dst.name} ({size_mb:.1f} MB)")

    # 7. English video (copy if exists)
    if results.get("video_en_path"):
        video_src = Path(results["video_en_path"])
        if video_src.exists():
            video_dst = archive_dir / f"{ticker_upper}_curated_video_en.mp4"
            shutil.copy2(video_src, video_dst)
            size_mb = video_dst.stat().st_size / (1024 * 1024)
            print(f"  → {video_dst.name} ({size_mb:.1f} MB)")

    # 8. Slides (copy directory if exists)
    if results.get("slides_dir"):
        slides_src = Path(results["slides_dir"])
        if slides_src.exists():
            slides_dst = archive_dir / "slides"
            if slides_dst.exists():
                shutil.rmtree(slides_dst)
            shutil.copytree(slides_src, slides_dst)
            slide_count = len(list(slides_dst.glob("slide_*.png")))
            print(f"  → slides/ ({slide_count} PNG images)")

    print(f"\n  Archive: {archive_dir}")
    return archive_dir


def run_pipeline(ticker: str, skip_video: bool = False, language: str = "both"):
    """Run the full pipeline for a ticker.

    Args:
        language: "zh" (Chinese only), "en" (English only), or "both" (default).
    """
    ticker = ticker.lower()
    ticker_upper = ticker.upper()
    company = get_company_name(ticker)

    lang_label = {"zh": "Chinese", "en": "English", "both": "Chinese + English"}[language]
    print(f"\n{'='*60}")
    print(f"  {ticker_upper} ({company}) — Full Curated Video Pipeline ({lang_label})")
    print(f"{'='*60}\n")

    # ── Step 1: Parse report ──────────────────────────────────
    print("[1/8] Parsing report...")
    report = _load_report(ticker)
    if not report:
        print(f"  ERROR: No report found for {ticker_upper}")
        return
    report_text = _build_report_text(report)
    print(f"  Report: {len(report.chapters)} chapters, {len(report_text)} chars")

    # ── Step 2: Recommend angles ──────────────────────────────
    print("\n[2/8] Recommending video angles (Gemini)...")
    angles = recommend_angles(ticker_upper, company, report_text)
    print(f"  Got {len(angles)} angles:")
    for i, a in enumerate(angles):
        score = a.get("score", {})
        total = sum(score.get(k, 0) for k in score if isinstance(score.get(k), (int, float)))
        print(f"    {i+1}. {a.get('angle_name', '?')} (score: {total})")
        print(f"       {a.get('core_thesis', '')[:80]}")

    # ── Step 3: Select best angle ─────────────────────────────
    print("\n[3/8] Selecting best angle...")
    # Pick highest total score
    best_idx = 0
    best_total = 0
    for i, a in enumerate(angles):
        score = a.get("score", {})
        total = sum(score.get(k, 0) for k in score if isinstance(score.get(k), (int, float)))
        if total > best_total:
            best_total = total
            best_idx = i
    selected = angles[best_idx]
    print(f"  Selected #{best_idx+1}: {selected.get('angle_name', '?')}")

    # ── Step 4: Curate document ───────────────────────────────
    print("\n[4/8] Curating document (Gemini)...")
    curated = curate_document(ticker_upper, company, report_text, selected)
    print(f"  Curated document: {len(curated)} chars")

    # ── Step 5: Generate video ────────────────────────────────
    video_path = None
    video_en_path = None
    if skip_video:
        print("\n[5/8] Video generation SKIPPED (--skip-video)")
    else:
        from webapp.state import SessionState

        # Create a temporary session object for the video generator
        session = SessionState.create(ticker, "xiaohongshu")
        session.video_angles = angles
        session.selected_angle_index = best_idx
        session.curated_document = curated

        # ── Chinese video ──
        if language in ("zh", "both"):
            print(f"\n[5a/8] Generating Chinese video (NotebookLM)...")
            print("  This may take 30-60 minutes...")
            try:
                from webapp.notebooklm import generate_curated_video
                video_path_obj = generate_curated_video(session)
                if video_path_obj:
                    video_path = str(video_path_obj)
                    size_mb = video_path_obj.stat().st_size / (1024 * 1024)
                    print(f"  Chinese video: {video_path} ({size_mb:.1f} MB)")
                else:
                    print("  WARNING: Chinese video generation returned None")
            except Exception as e:
                print(f"  ERROR: Chinese video generation failed: {e}")

        # ── English video ──
        if language in ("en", "both"):
            print(f"\n[5b/8] Generating English video (NotebookLM)...")
            print("  This may take 30-60 minutes...")
            try:
                from webapp.notebooklm import generate_curated_video_english
                video_en_path_obj = generate_curated_video_english(session)
                if video_en_path_obj:
                    video_en_path = str(video_en_path_obj)
                    size_mb = video_en_path_obj.stat().st_size / (1024 * 1024)
                    print(f"  English video: {video_en_path} ({size_mb:.1f} MB)")
                else:
                    print("  WARNING: English video generation returned None")
            except Exception as e:
                print(f"  ERROR: English video generation failed: {e}")

        session.delete()

    # ── Step 6: Generate XHS slides ──────────────────────────
    slides_dir = None
    print("\n[6/8] Generating XHS slides...")
    try:
        from platforms.xiaohongshu.generate_slides import generate_slides_from_curated
        slides_dir = generate_slides_from_curated(
            ticker=ticker_upper,
            company_name=company,
            curated_document=curated,
            angle=selected,
        )
        slide_count = len(list(slides_dir.glob("slide_*.png")))
        print(f"  Generated {slide_count} slide images in {slides_dir}")
    except Exception as e:
        print(f"  ERROR: Slide generation failed: {e}")

    # ── Step 7: Generate XHS post ─────────────────────────────
    print("\n[7/8] Generating XHS post content...")
    try:
        from platforms.xiaohongshu.generate_caption import generate_caption
        caption_result = generate_caption(
            ticker=ticker_upper,
            company_name=company,
            curated_document=curated,
            angle=selected,
        )
        xhs_post = f"{caption_result['title']}\n\n{caption_result['body']}"
    except Exception as e:
        print(f"  Caption generation failed: {e}, using fallback")
        xhs_post = _generate_xhs_post(ticker_upper, selected)
    print(f"  Post content:\n{'─'*40}")
    for line in xhs_post.split("\n"):
        print(f"  {line}")
    print(f"{'─'*40}")

    # ── Step 8: Archive ───────────────────────────────────────
    print("\n[8/8] Archiving results...")
    results = {
        "angles": angles,
        "selected_angle": selected,
        "curated_document": curated,
        "xhs_post": xhs_post,
        "video_path": video_path,
        "video_en_path": video_en_path,
        "slides_dir": str(slides_dir) if slides_dir else None,
    }
    archive_dir = _archive_results(ticker, results)

    print(f"\n{'='*60}")
    print(f"  Pipeline complete for {ticker_upper}")
    print(f"{'='*60}")

    return archive_dir


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    ticker = args[0].lower()
    if ticker not in AVAILABLE_TICKERS:
        print(f"Unknown ticker: {ticker}. Available: {', '.join(AVAILABLE_TICKERS)}")
        sys.exit(1)

    skip_video = "--skip-video" in args

    language = "both"
    if "--language" in args:
        lang_idx = args.index("--language")
        if lang_idx + 1 < len(args):
            language = args[lang_idx + 1]
            if language not in ("zh", "en", "both"):
                print(f"Invalid language: {language}. Use zh, en, or both.")
                sys.exit(1)

    run_pipeline(ticker, skip_video=skip_video, language=language)
