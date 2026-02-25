"""
Shared content strategist: unified angle selection + 30K curation.

Extracts the common content strategy pipeline used by Xueqiu, Xiaohongshu,
and the video/webapp pipeline into a single engine module.

Functions:
    preprocess_markdown()   - Strip noise from raw markdown
    build_report_text()     - Get full text from ReportData
    recommend_angles()      - Gemini reads report → selects angles
    extract_chapters()      - Pull chapter text by numeric refs
    curate_content()        - Gemini curates 30K+ focused document
    parse_strategy_json()   - Robust JSON parsing from Gemini output
    format_angle_for_prompt() - Format ContentAngle as readable text
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.report_schema import ReportData
from engine.config import GEMINI_MODEL, get_company_name

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


# ── Dataclasses ──────────────────────────────────────────────────────

@dataclass
class ContentAngle:
    angle_name: str = ""
    thesis: str = ""
    why_this_angle: str = ""
    chapter_refs: list[int] = field(default_factory=list)
    key_data_points: list[str] = field(default_factory=list)
    discussion_anchors: list[str] = field(default_factory=list)
    score: dict = field(default_factory=dict)        # 5-dimension scores (optional)
    extra: dict = field(default_factory=dict)         # Platform-specific (hook_type, recommended_charts, etc.)

    def to_dict(self) -> dict:
        d = {
            "angle_name": self.angle_name,
            "core_thesis": self.thesis,  # backward compat with webapp templates
            "thesis": self.thesis,
            "why_this_angle": self.why_this_angle,
            "chapter_refs": self.chapter_refs,
            "key_data_points": self.key_data_points,
            "discussion_anchors": self.discussion_anchors,
            "score": self.score,
        }
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ContentAngle:
        known_keys = {
            "angle_name", "thesis", "why_this_angle", "chapter_refs",
            "key_data_points", "discussion_anchors", "score",
            # core_thesis is consumed by thesis field
            "core_thesis",
        }
        extra = {k: v for k, v in d.items() if k not in known_keys}
        return cls(
            angle_name=d.get("angle_name", ""),
            thesis=d.get("thesis", "") or d.get("core_thesis", ""),
            why_this_angle=d.get("why_this_angle", ""),
            chapter_refs=d.get("chapter_refs", []),
            key_data_points=d.get("key_data_points", []),
            discussion_anchors=d.get("discussion_anchors", []),
            score=d.get("score", {}),
            extra=extra,
        )


@dataclass
class StrategyResult:
    angles: list[ContentAngle] = field(default_factory=list)
    rationale: str = ""
    raw_json: dict = field(default_factory=dict)


# ── Preprocessing ────────────────────────────────────────────────────

def preprocess_markdown(raw: str, max_chars: int = 800_000) -> str:
    """Strip noise from raw markdown to fit in Gemini's context window.

    Removes: [DM-xxx] tags, mermaid/code blocks, appendix sections,
    table separator lines, compresses whitespace. Hard cap at max_chars.
    """
    text = raw

    # Strip [DM-xxx] reference tags
    text = re.sub(r"\[DM-[^\]]+\]", "", text)

    # Strip reference tags like [硬数据: ...] [合理推断: ...]
    text = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", text)

    # Strip mermaid code blocks
    text = re.sub(r"```mermaid\s*\n.*?```", "", text, flags=re.DOTALL)

    # Strip other diagram code blocks
    text = re.sub(r"```(?:graph|flowchart|dot|plantuml)\s*\n.*?```", "", text, flags=re.DOTALL)

    # Strip ASCII art (lines of dashes/pipes)
    text = re.sub(r"(?m)^[│├└┌┐┘┤┬┴┼─]{3,}.*$", "", text)

    # Compress table separator lines (|---|---|) to a single marker
    text = re.sub(r"^\|[\s:|-]+\|$", "|---|", text, flags=re.MULTILINE)

    # Compress runs of 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Hard cap with smart truncation
    if len(text) > max_chars:
        cut_point = text.rfind("\n## ", 0, max_chars)
        if cut_point > max_chars * 3 // 4:
            text = text[:cut_point] + "\n\n[…报告后续章节已截断]"
        else:
            text = text[:max_chars] + "\n\n[…已截断]"

    return text


def build_report_text(report: ReportData, preprocess: bool = True) -> str:
    """Get full report text: preprocessed raw_markdown or joined chapters."""
    if report.raw_markdown:
        text = report.raw_markdown
        if preprocess:
            text = preprocess_markdown(text)
        return text

    # Fallback: join chapter content
    parts = []
    for ch in report.chapters:
        parts.append(f"# {ch.title}\n\n{ch.content_markdown}")
    return "\n\n".join(parts)


# ── JSON parsing ─────────────────────────────────────────────────────

def parse_strategy_json(raw: str) -> Optional[dict]:
    """Robustly parse JSON from Gemini strategy response.

    Handles markdown code fences and extracts the first valid JSON object
    containing either a "posts" key (Xueqiu format) or a JSON array (video format).
    """
    text = raw.strip()

    # Strip markdown code fences
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    text = text.strip()

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, (dict, list)):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: extract first JSON object or array
    for pattern in [r"\{[\s\S]+\}", r"\[[\s\S]+\]"]:
        match = re.search(pattern, text)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, (dict, list)):
                    return result
            except json.JSONDecodeError:
                continue

    log.warning("Failed to parse strategy JSON response")
    return None


# ── Angle recommendation ─────────────────────────────────────────────

def recommend_angles(
    report: ReportData,
    platform_instructions: str = "",
    chart_catalog: str = "",
    max_angles: int = 3,
) -> Optional[StrategyResult]:
    """Call Gemini with the full report to recommend content angles.

    Args:
        report: Parsed report data.
        platform_instructions: Platform-specific prompt section injected
            into {platform_section} (e.g. Xueqiu chart rules, hook types).
        chart_catalog: Formatted chart catalog text for {extra_inputs}.
        max_angles: Maximum angles to recommend.

    Returns:
        StrategyResult or None on failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        return None

    full_text = build_report_text(report)
    if len(full_text) < 500:
        log.warning("Report text too short for angle recommendation (%d chars)", len(full_text))
        return None

    prompt_template = (_PROMPTS_DIR / "angle_recommend.md").read_text(encoding="utf-8")

    company_name = get_reliable_company_name(report)
    word_count = len(full_text)

    # Build extra_inputs (chart catalog, etc.)
    extra_inputs = ""
    if chart_catalog:
        extra_inputs = f"### 图表目录\n\n{chart_catalog}"
    else:
        extra_inputs = "(无图表目录)"

    prompt = prompt_template.format(
        ticker=report.metadata.ticker.upper(),
        company_name=company_name,
        word_count=word_count,
        max_angles=max_angles,
        platform_section=platform_instructions or "(无平台特殊要求)",
        extra_inputs=extra_inputs,
        full_report=full_text,
    )

    log.info("Calling angle recommender (%d chars prompt, ~%d tokens est.)",
             len(prompt), len(prompt) // 4)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        raw = response.text.strip()
    except Exception as e:
        log.error("Angle recommendation call failed: %s", e)
        return None

    parsed = parse_strategy_json(raw)
    if parsed is None:
        return None

    return _parsed_json_to_strategy_result(parsed, max_angles)


def _parsed_json_to_strategy_result(parsed: dict | list, max_angles: int) -> StrategyResult:
    """Convert parsed JSON (either Xueqiu dict or video list format) to StrategyResult."""
    # Xueqiu format: {"posts": [...], "rationale": "..."}
    if isinstance(parsed, dict) and "posts" in parsed:
        angles = []
        for post in parsed["posts"][:max_angles]:
            angle = ContentAngle(
                angle_name=post.get("post_id", ""),
                thesis=post.get("thesis", ""),
                why_this_angle=post.get("rationale", "") or parsed.get("rationale", ""),
                chapter_refs=post.get("chapter_refs", []),
                key_data_points=post.get("key_data_points", []),
                discussion_anchors=[],
                score={},
                extra={
                    k: v for k, v in post.items()
                    if k not in ("post_id", "thesis", "rationale", "chapter_refs",
                                 "key_data_points", "_chart_note")
                },
            )
            angles.append(angle)
        return StrategyResult(
            angles=angles,
            rationale=parsed.get("rationale", ""),
            raw_json=parsed,
        )

    # Video format: [{"angle_name": ..., "score": {...}}, ...]
    if isinstance(parsed, list):
        angles = []
        for item in parsed[:max_angles]:
            angle = ContentAngle.from_dict(item)
            angles.append(angle)
        return StrategyResult(
            angles=angles,
            rationale="",
            raw_json={"angles": parsed},
        )

    # Unknown format
    log.warning("Unknown strategy JSON format: %s", type(parsed))
    return StrategyResult(raw_json=parsed if isinstance(parsed, dict) else {})


# ── Chapter extraction ───────────────────────────────────────────────

def extract_chapters(report: ReportData, chapter_refs: list[int]) -> str:
    """Extract full chapter text by numeric references.

    chapter_refs are 1-based chapter numbers. Tries multiple title patterns:
    - "第N章" (e.g. "第2章：财务全景")
    - "ChN:" (e.g. "Ch2: 财务全景")
    - "N. " prefix (e.g. "2. 财务全景")
    - Fallback: by list index (0-based)
    """
    parts = []
    for ref in chapter_refs:
        found = False
        targets = [f"第{ref}章", f"Ch{ref}:", f"Ch{ref}："]
        for ch in report.chapters:
            if any(t in ch.title for t in targets):
                content = _clean_chapter_text(ch.content_markdown)
                parts.append(f"=== {ch.title} ===\n\n{content}")
                found = True
                break

        if not found:
            prefix = f"{ref}. "
            for ch in report.chapters:
                if ch.title.startswith(prefix):
                    content = _clean_chapter_text(ch.content_markdown)
                    parts.append(f"=== {ch.title} ===\n\n{content}")
                    found = True
                    break

        if not found:
            idx = ref - 1
            if 0 <= idx < len(report.chapters):
                ch = report.chapters[idx]
                content = _clean_chapter_text(ch.content_markdown)
                parts.append(f"=== {ch.title} ===\n\n{content}")

    return "\n\n".join(parts)


def _clean_chapter_text(content: str) -> str:
    """Remove reference tags and mermaid blocks from chapter content."""
    content = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", content)
    content = re.sub(r"```mermaid\s*\n.*?```", "", content, flags=re.DOTALL)
    return content


# ── Content curation ─────────────────────────────────────────────────

def curate_content(
    report: ReportData,
    angle: ContentAngle,
    target_chars: int = 30_000,
    platform_instructions: str = "",
) -> Optional[str]:
    """Call Gemini to curate a focused document from the full report.

    Produces a ~30K+ char document organized around the selected angle,
    suitable as rich source material for downstream generators (Xueqiu writer,
    XHS slides, NotebookLM video, etc.).

    Args:
        report: Parsed report data.
        angle: The selected content angle.
        target_chars: Target document length (default 30K).
        platform_instructions: Context about how the curated doc will be used.

    Returns:
        Curated markdown document, or None on failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        return None

    full_text = build_report_text(report)
    if len(full_text) < 500:
        log.warning("Report text too short for curation")
        return None

    prompt_template = (_PROMPTS_DIR / "content_curation.md").read_text(encoding="utf-8")

    company_name = get_reliable_company_name(report)
    angle_text = format_angle_for_prompt(angle)

    prompt = prompt_template.format(
        ticker=report.metadata.ticker.upper(),
        company_name=company_name,
        word_count=len(full_text),
        target_chars=target_chars,
        selected_angle=angle_text,
        platform_usage_context=platform_instructions or "(通用深度内容)",
        report_content=full_text,
    )

    log.info("Calling content curator (%d chars prompt)", len(prompt))

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=65536,
                temperature=1.0,
            ),
        )
        curated = response.text

        from engine.content_filter import clean_generated_content
        curated = clean_generated_content(curated)

        log.info("Curated document: %d chars", len(curated))
        return curated
    except Exception as e:
        log.error("Content curation failed: %s", e)
        return None


# ── Formatting helpers ───────────────────────────────────────────────

def format_angle_for_prompt(angle: ContentAngle) -> str:
    """Format a ContentAngle as readable text for injection into prompts."""
    parts = [
        f"**角度名称**: {angle.angle_name}",
        f"**核心论点**: {angle.thesis}",
    ]

    if angle.why_this_angle:
        parts.append(f"**选择理由**: {angle.why_this_angle}")

    if angle.key_data_points:
        parts.append("**核心数据点**:")
        for dp in angle.key_data_points:
            parts.append(f"  - {dp}")

    if angle.discussion_anchors:
        parts.append("**讨论锚点**:")
        for i, a in enumerate(angle.discussion_anchors, 1):
            parts.append(f"  {i}. {a}")

    if angle.chapter_refs:
        refs_str = ", ".join(str(r) for r in angle.chapter_refs)
        parts.append(f"**引用章节**: {refs_str}")

    # Platform-specific extras
    hook_type = angle.extra.get("hook_type", "")
    if hook_type:
        parts.append(f"**Hook类型**: {hook_type}")

    title_hook = angle.extra.get("title_hook", "")
    if title_hook:
        parts.append(f"**开头钩子**: {title_hook}")

    aha = angle.extra.get("audience_aha_moment", "")
    if aha:
        parts.append(f"**观众新认知**: {aha}")

    if angle.score:
        parts.append("**评分**:")
        labels = {
            "information_delta": "信息增量",
            "controversy_tension": "争议张力",
            "data_density": "数据密度",
            "narrative_potential": "叙事潜力",
            "timeliness": "时效相关",
        }
        for key, label in labels.items():
            val = angle.score.get(key, "")
            if val:
                parts.append(f"  - {label}: {val}/10")

    return "\n".join(parts)


# ── Internal helpers ─────────────────────────────────────────────────

def get_reliable_company_name(report: ReportData) -> str:
    """Get reliable company name: prefer config mapping, fall back to parsed."""
    ticker = report.metadata.ticker.upper()
    mapped = get_company_name(ticker)
    if mapped != ticker:
        return mapped
    parsed = report.metadata.company_name
    if parsed and len(parsed) > 1 and not any(c.isdigit() for c in parsed[:3]):
        return parsed
    return ticker
