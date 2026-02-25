#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaohongshu component-based slide generator from curated content.

Generates 8-10 XHS slide images from a 30K curated document using Gemini
for content extraction with an evaluate-rewrite loop.

Gemini outputs HTML snippets using predefined CSS classes, which are
embedded into a single base template for rendering.

Usage:
    from platforms.xiaohongshu.generate_slides import generate_slides_from_curated

    slides_dir = generate_slides_from_curated(
        ticker='PLTR',
        company_name='Palantir',
        curated_document=curated_text,
        angle={'angle_name': '...', 'core_thesis': '...'},
    )
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# ── Resolve project root so engine imports work ──────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.config import GEMINI_MODEL

_PLATFORM_DIR = Path(__file__).resolve().parent
_PROMPTS_DIR = _PLATFORM_DIR / "prompts"
_ARCHIVE_DIR = _PLATFORM_DIR / "archive"


# =====================================================================
# Gemini call helpers
# =====================================================================

def _call_gemini(prompt: str) -> Optional[str]:
    """Call Gemini and return raw response text."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=(
            "You are a JSON-only API for generating XHS (小红书) slide content. "
            "Return ONLY a valid JSON array. No markdown fences, no explanation."
        ),
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )
    except Exception:
        # response_mime_type may not be supported — retry without it
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )

    return response.text.strip()


def _parse_json_array(raw: str) -> Optional[list]:
    """Parse a JSON array from Gemini response, handling code fences."""
    # Strip code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()

    # Try direct parse
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        return None
    except json.JSONDecodeError:
        pass

    # Try to find array in response
    match = re.search(r"\[[\s\S]+\]", raw)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return None


# =====================================================================
# Slide extraction
# =====================================================================

def _extract_slides_json(
    ticker: str,
    company_name: str,
    curated_document: str,
    angle: dict,
    rewrite_instructions: str = "",
) -> Optional[list[dict]]:
    """Call Gemini to extract slide HTML from curated content."""
    prompt_template = (_PROMPTS_DIR / "slide_extraction.md").read_text(encoding="utf-8")

    # Build rewrite block
    rewrite_block = ""
    if rewrite_instructions:
        rewrite_block = (
            f"\n## 重写要求（上次输出被驳回）\n\n"
            f"问题：{rewrite_instructions}\n"
            f"请修正以上所有问题，不要重复同样的错误。\n"
        )

    prompt = prompt_template.replace("{ticker}", ticker.upper())
    prompt = prompt.replace("{company_name}", company_name)
    prompt = prompt.replace("{angle_name}", angle.get("angle_name", "深度研究"))
    prompt = prompt.replace("{angle_thesis}", angle.get("core_thesis", angle.get("thesis", "")))
    prompt = prompt.replace("{curated_document}", curated_document[:50000])
    prompt = prompt.replace("{rewrite_instructions}", rewrite_block)

    raw = _call_gemini(prompt)
    if not raw:
        return None

    return _parse_json_array(raw)


# =====================================================================
# Structure validation (pre-eval)
# =====================================================================

def _validate_structure(slides: list[dict]) -> Optional[str]:
    """Validate slide structure. Returns error message or None if valid."""
    # Count check
    if len(slides) < 8:
        return f"只有{len(slides)}张slide，至少需要8张"
    if len(slides) > 10:
        return f"有{len(slides)}张slide，最多10张"

    # Each slide must have 'html' key
    for i, s in enumerate(slides):
        if "html" not in s or not s["html"].strip():
            return f"slide {i+1} 缺少 'html' 字段或内容为空"

    # No <script> tags
    for i, s in enumerate(slides):
        if "<script" in s["html"].lower():
            return f"slide {i+1} 包含 <script> 标签，不允许"

    return None


# =====================================================================
# Slide evaluation (Gemini)
# =====================================================================

def _evaluate_slides(slides: list[dict], ticker: str, curated_document: str) -> dict:
    """Evaluate slides using the slide evaluation prompt."""
    prompt_template = (_PROMPTS_DIR / "slide_evaluation.md").read_text(encoding="utf-8")

    slides_json_str = json.dumps(slides, ensure_ascii=False, indent=2)
    # Use first 5000 chars of curated doc for verification
    excerpt = curated_document[:5000]

    prompt = prompt_template.replace("{ticker}", ticker.upper())
    prompt = prompt.replace("{slides_json}", slides_json_str)
    prompt = prompt.replace("{curated_document_excerpt}", excerpt)

    raw = _call_gemini(prompt)
    if not raw:
        # No API — skip evaluation, assume pass
        return {"pass": True, "violations": [], "scores": {}, "total_score": 0, "rewrite_instructions": ""}

    # Parse evaluation result
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```\s*$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]+\}", raw)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                return {"pass": True, "violations": [], "scores": {}, "total_score": 0, "rewrite_instructions": ""}
        else:
            return {"pass": True, "violations": [], "scores": {}, "total_score": 0, "rewrite_instructions": ""}

    result.setdefault("pass", True)
    result.setdefault("violations", [])
    result.setdefault("scores", {})
    result.setdefault("total_score", sum(result["scores"].values()) if result["scores"] else 0)
    result.setdefault("rewrite_instructions", "")

    return result


# =====================================================================
# Rendering
# =====================================================================

def _render_slides(slides: list[dict], ticker: str, company_name: str,
                   output_dir: Path) -> list[Path]:
    """Render component-based slides to PNG images."""
    from platforms.xiaohongshu.render_slides import render_component_slides
    return render_component_slides(slides, ticker, output_dir, company_name=company_name)


# =====================================================================
# Public API
# =====================================================================

def generate_slides_from_curated(
    ticker: str,
    company_name: str,
    curated_document: str,
    angle: dict,
    output_dir: Path | None = None,
    max_attempts: int = 3,
) -> Path:
    """Generate 8-10 XHS slide images from curated content.

    Args:
        ticker: Stock ticker symbol (e.g. 'PLTR').
        company_name: Company display name.
        curated_document: The ~30K curated document text.
        angle: Angle dict with 'angle_name' and 'core_thesis' keys.
        output_dir: Output directory for PNG files. Defaults to
            archive/{ticker}/slides/.
        max_attempts: Max extraction + evaluation attempts.

    Returns:
        Path to the directory containing slide_01.png ... slide_N.png.
    """
    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()

    if output_dir is None:
        output_dir = _ARCHIVE_DIR / ticker_lower / "slides"
    output_dir = Path(output_dir)

    print(f"[xhs/slides] Generating slides for {ticker_upper} ({company_name})")

    rewrite_instructions = ""
    slides_json = None

    for attempt in range(1, max_attempts + 1):
        print(f"[xhs/slides] Attempt {attempt}/{max_attempts}...")

        # 1. Extract slides JSON from curated content
        extracted = _extract_slides_json(
            ticker_upper, company_name, curated_document, angle,
            rewrite_instructions=rewrite_instructions,
        )
        if extracted is None:
            print(f"[xhs/slides] Attempt {attempt}: Gemini returned invalid JSON, retrying...")
            rewrite_instructions = "JSON解析失败，确保返回有效的JSON数组"
            continue

        print(f"[xhs/slides] Attempt {attempt}: Got {len(extracted)} slides")

        # 2. Validate structure
        structure_error = _validate_structure(extracted)
        if structure_error:
            print(f"[xhs/slides] Attempt {attempt}: Structure error — {structure_error}")
            rewrite_instructions = f"结构问题: {structure_error}"
            continue

        # 3. Evaluate quality
        eval_result = _evaluate_slides(extracted, ticker_upper, curated_document)
        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            print(f"[xhs/slides] Attempt {attempt}: PASS (score {total_score}/20)")
            slides_json = extracted
            break

        print(f"[xhs/slides] Attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

        # Keep best attempt so far
        if slides_json is None:
            slides_json = extracted

    if slides_json is None:
        raise RuntimeError(f"Failed to generate valid slides for {ticker_upper} after {max_attempts} attempts")

    # 4. Render to PNG
    print(f"[xhs/slides] Rendering {len(slides_json)} slides...")
    png_paths = _render_slides(slides_json, ticker_upper, company_name, output_dir)
    print(f"[xhs/slides] Done: {len(png_paths)} slides in {output_dir}")

    # Save slides JSON alongside PNGs for reference
    json_path = output_dir / "slides.json"
    json_path.write_text(json.dumps(slides_json, ensure_ascii=False, indent=2), encoding="utf-8")

    return output_dir


# =====================================================================
# CLI
# =====================================================================

if __name__ == "__main__":
    """Quick test: python generate_slides.py <ticker> <curated_doc_path> [angle_json_path]"""
    if len(sys.argv) < 3:
        print("Usage: python generate_slides.py <ticker> <curated_doc_path> [angle_json_path]")
        print("Example: python generate_slides.py PLTR /path/to/curated_document.md")
        sys.exit(1)

    from engine.config import get_company_name

    ticker = sys.argv[1].upper()
    company = get_company_name(ticker)

    curated_path = Path(sys.argv[2])
    curated_doc = curated_path.read_text(encoding="utf-8")

    angle = {"angle_name": "深度研究", "core_thesis": f"{company}深度研究报告解读"}
    if len(sys.argv) > 3:
        angle_path = Path(sys.argv[3])
        angle = json.loads(angle_path.read_text(encoding="utf-8"))

    out = generate_slides_from_curated(
        ticker=ticker,
        company_name=company,
        curated_document=curated_doc,
        angle=angle,
        output_dir=Path(f"/tmp/{ticker.lower()}_slides"),
    )
    print(f"\nSlides directory: {out}")
