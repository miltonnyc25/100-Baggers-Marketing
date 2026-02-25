#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaohongshu caption generator from curated content.

Generates a title + body caption for XHS slide/video posts from a 30K
curated document using Gemini with an evaluate-rewrite loop.

Usage:
    from platforms.xiaohongshu.generate_caption import generate_caption

    result = generate_caption(
        ticker='PLTR',
        company_name='Palantir',
        curated_document=curated_text,
        angle={'angle_name': '...', 'core_thesis': '...'},
    )
    # result = {"title": "...", "body": "..."}
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
_CONFIG_PATH = _PLATFORM_DIR / "config.json"
_ARCHIVE_DIR = _PLATFORM_DIR / "archive"


# =====================================================================
# Config helpers
# =====================================================================

def _load_config() -> dict:
    """Load XHS platform config."""
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


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
            "You are a JSON-only API for generating XHS (小红书) post captions. "
            "Return ONLY a valid JSON object with 'title' and 'body' fields. "
            "No markdown fences, no explanation."
        ),
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
    except Exception:
        # response_mime_type may not be supported — retry without it
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4096,
            ),
        )

    return response.text.strip()


def _parse_json_object(raw: str) -> Optional[dict]:
    """Parse a JSON object from Gemini response, handling code fences."""
    # Strip code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()

    # Try direct parse
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return None
    except json.JSONDecodeError:
        pass

    # Try to find object in response
    match = re.search(r"\{[\s\S]+\}", raw)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


# =====================================================================
# Validation
# =====================================================================

def _count_chars(text: str) -> int:
    """Count characters in text (Chinese-aware)."""
    return len(text)


def _validate_caption(result: dict, ticker: str) -> Optional[str]:
    """Validate caption result. Returns error message or None if valid."""
    config = _load_config()

    # Must have title and body
    if "title" not in result or not result["title"].strip():
        return "缺少 title 字段"
    if "body" not in result or not result["body"].strip():
        return "缺少 body 字段"

    title = result["title"].strip()
    body = result["body"].strip()

    # Title length check
    if _count_chars(title) > 20:
        return f"标题过长: {_count_chars(title)}字符，最多20字符"

    # Body length check
    body_len = _count_chars(body)
    if body_len < 600:
        return f"正文过短: {body_len}字符，至少600字符"
    if body_len > 1000:
        return f"正文过长: {body_len}字符，最多1000字符"

    # Must contain hashtags
    if "#" not in body:
        return "正文缺少 hashtags"

    # Must contain disclaimer
    if "不构成投资建议" not in body:
        return "正文缺少免责声明"

    # Sensitive topics check
    sensitive = config.get("compliance", {}).get("sensitive_topics", [])
    full_text = title + body
    for topic in sensitive:
        if topic in full_text:
            return f"包含敏感词: {topic}"

    # No price targets or investment advice (use word boundaries to avoid false positives)
    advice_patterns = [
        r"目标价", r"建议买入", r"建议卖出", r"建议持有",
        r"推荐买入", r"推荐卖出", r"应该买", r"应该卖",
    ]
    for pattern in advice_patterns:
        if re.search(pattern, full_text):
            return f"包含投资建议: {pattern}"

    return None


# =====================================================================
# Caption extraction
# =====================================================================

def _extract_caption(
    ticker: str,
    company_name: str,
    curated_document: str,
    angle: dict,
    rewrite_instructions: str = "",
) -> Optional[dict]:
    """Call Gemini to generate caption from curated content."""
    prompt_template = (_PROMPTS_DIR / "caption_prompt.md").read_text(encoding="utf-8")

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

    return _parse_json_object(raw)


# =====================================================================
# Template fallback
# =====================================================================

def _fallback_caption(ticker: str, company_name: str, angle: dict) -> dict:
    """Generate a minimal caption from angle data when Gemini fails."""
    config = _load_config()
    name = angle.get("angle_name", "深度研究")
    thesis = angle.get("core_thesis", angle.get("thesis", f"{company_name}深度研究报告解读"))

    title = f"📊 {ticker} {name}"
    if _count_chars(title) > 20:
        title = title[:20]

    hashtags_list = config.get("hashtags", ["美股", "投资分析"])
    base_tags = f"#深度研报 #{ticker} #{company_name} #美股 #投资分析"
    extra_tags = " ".join(f"#{t}" for t in hashtags_list if t not in base_tags)
    all_tags = f"{base_tags} {extra_tags}".strip()

    body = (
        f"📊 {thesis}\n\n"
        f"深度研究报告核心发现——\n\n"
        f"👉 完整深度报告: https://www.100baggers.club/zh/reports/{ticker.lower()}\n\n"
        f"{all_tags}\n\n"
        f"⚠️ 信息整理，不构成投资建议"
    )

    return {"title": title, "body": body}


# =====================================================================
# Public API
# =====================================================================

def generate_caption(
    ticker: str,
    company_name: str,
    curated_document: str,
    angle: dict,
    max_attempts: int = 3,
) -> dict:
    """Generate an XHS caption (title + body) from curated content.

    Args:
        ticker: Stock ticker symbol (e.g. 'PLTR').
        company_name: Company display name.
        curated_document: The ~30K curated document text.
        angle: Angle dict with 'angle_name' and 'core_thesis' keys.
        max_attempts: Max extraction + validation attempts.

    Returns:
        Dict with 'title' and 'body' keys.
    """
    ticker_upper = ticker.upper()

    print(f"[xhs/caption] Generating caption for {ticker_upper} ({company_name})")

    rewrite_instructions = ""

    for attempt in range(1, max_attempts + 1):
        print(f"[xhs/caption] Attempt {attempt}/{max_attempts}...")

        # 1. Extract caption JSON from curated content
        extracted = _extract_caption(
            ticker_upper, company_name, curated_document, angle,
            rewrite_instructions=rewrite_instructions,
        )
        if extracted is None:
            print(f"[xhs/caption] Attempt {attempt}: Gemini returned invalid JSON, retrying...")
            rewrite_instructions = "JSON解析失败，确保返回有效的JSON对象，包含title和body字段"
            continue

        print(f"[xhs/caption] Attempt {attempt}: Got title='{extracted.get('title', '')[:30]}...'")

        # 2. Validate
        error = _validate_caption(extracted, ticker_upper)
        if error is None:
            print(f"[xhs/caption] Attempt {attempt}: PASS")
            return extracted

        print(f"[xhs/caption] Attempt {attempt}: FAIL — {error}")
        rewrite_instructions = error

    # All attempts failed — use fallback
    print(f"[xhs/caption] All {max_attempts} attempts failed, using template fallback")
    return _fallback_caption(ticker_upper, company_name, angle)


# =====================================================================
# CLI
# =====================================================================

if __name__ == "__main__":
    """Usage: python generate_caption.py <ticker> <curated_doc_path> [angle_json_path] [--save]"""
    if len(sys.argv) < 3:
        print("Usage: python generate_caption.py <ticker> <curated_doc_path> [angle_json_path] [--save]")
        print("Example: python generate_caption.py PLTR /path/to/curated_document.md --save")
        sys.exit(1)

    from datetime import datetime
    from engine.config import get_company_name

    save_flag = "--save" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--save"]

    ticker = args[0].upper()
    company = get_company_name(ticker)

    curated_path = Path(args[1])
    curated_doc = curated_path.read_text(encoding="utf-8")

    angle = {"angle_name": "深度研究", "core_thesis": f"{company}深度研究报告解读"}
    if len(args) > 2:
        angle_path = Path(args[2])
        angle = json.loads(angle_path.read_text(encoding="utf-8"))

    result = generate_caption(
        ticker=ticker,
        company_name=company,
        curated_document=curated_doc,
        angle=angle,
    )

    # Display
    print(f"\n{'='*60}")
    print(f"Title ({_count_chars(result['title'])} chars):")
    print(f"  {result['title']}")
    print(f"\nBody ({_count_chars(result['body'])} chars):")
    print(f"{'─'*60}")
    for line in result["body"].split("\n"):
        print(f"  {line}")
    print(f"{'─'*60}")

    # Save to archive
    if save_flag:
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_dir = _ARCHIVE_DIR / ticker.lower()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{date_str}_xhs_caption.md"
        content = f"{result['title']}\n\n{result['body']}"
        out_path.write_text(content, encoding="utf-8")
        print(f"\nSaved to: {out_path}")
