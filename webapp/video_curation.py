"""
Video curation pipeline: angle recommendation + document curation.

Step 1: Gemini reads full report → recommends 2-3 video angles with 5-dimension scoring.
Step 2: User picks an angle → Gemini curates a 30,000+ char document from the report.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import google.generativeai as genai

from engine.config import GEMINI_MODEL
from engine.content_filter import clean_generated_content

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))


def recommend_angles(ticker: str, company_name: str, report_content: str) -> list[dict]:
    """Call Gemini to recommend 2-3 video angles from the full report.

    Returns a list of angle dicts with scores.
    """
    prompt_template = (_PROMPTS_DIR / "video_angle_recommend.md").read_text(encoding="utf-8")
    word_count = len(report_content)
    prompt = prompt_template.replace("{ticker}", ticker.upper())
    prompt = prompt.replace("{company_name}", company_name)
    prompt = prompt.replace("{word_count}", str(word_count))
    prompt = prompt.replace("{report_content}", report_content)

    model = genai.GenerativeModel(GEMINI_MODEL)

    # Try with JSON response mime type first
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        angles = json.loads(response.text)
        if isinstance(angles, list) and len(angles) > 0:
            log.info("Got %d angle recommendations (JSON mode)", len(angles))
            return angles
    except Exception:
        log.warning("JSON mode failed, retrying without response_mime_type")

    # Fallback: no response_mime_type, parse JSON from text
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=4096,
        ),
    )
    text = response.text
    # Extract JSON array from markdown code fences if present
    json_match = re.search(r"```(?:json)?\s*\n(\[.*?\])\s*\n```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    angles = json.loads(text)
    log.info("Got %d angle recommendations (text mode)", len(angles))
    return angles


def curate_document(
    ticker: str, company_name: str, report_content: str, selected_angle: dict,
) -> str:
    """Call Gemini to curate a 30k+ char document for the selected angle.

    Returns the curated markdown document.
    """
    prompt_template = (_PROMPTS_DIR / "video_curation.md").read_text(encoding="utf-8")
    word_count = len(report_content)
    angle_text = _format_angle_for_prompt(selected_angle)

    prompt = prompt_template.replace("{ticker}", ticker.upper())
    prompt = prompt.replace("{company_name}", company_name)
    prompt = prompt.replace("{word_count}", str(word_count))
    prompt = prompt.replace("{selected_angle}", angle_text)
    prompt = prompt.replace("{report_content}", report_content)

    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=65536,
            temperature=1.0,
        ),
    )

    curated = response.text
    curated = clean_generated_content(curated)
    log.info("Curated document: %d chars", len(curated))
    return curated


def _format_angle_for_prompt(angle: dict) -> str:
    """Format an angle dict as readable text for the curation prompt's {selected_angle}."""
    parts = [
        f"**角度名称**: {angle.get('angle_name', '')}",
        f"**核心论点**: {angle.get('core_thesis', '')}",
        f"**选择理由**: {angle.get('why_this_angle', '')}",
    ]

    anchors = angle.get("discussion_anchors", [])
    if anchors:
        parts.append("**讨论锚点**:")
        for i, a in enumerate(anchors, 1):
            parts.append(f"  {i}. {a}")

    aha = angle.get("audience_aha_moment", "")
    if aha:
        parts.append(f"**观众顿悟时刻**: {aha}")

    scores = angle.get("score", {})
    if scores:
        parts.append("**评分**:")
        labels = {
            "information_delta": "信息增量",
            "controversy_tension": "争议张力",
            "data_density": "数据密度",
            "narrative_potential": "叙事潜力",
            "timeliness": "时效相关",
        }
        for key, label in labels.items():
            val = scores.get(key, "")
            if val:
                parts.append(f"  - {label}: {val}/10")

    return "\n".join(parts)
