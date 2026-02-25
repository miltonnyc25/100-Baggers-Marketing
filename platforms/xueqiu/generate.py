#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xueqiu (雪球) long-form post generator.

Two-stage intelligent pipeline:
  Stage 1 (Strategist): Full markdown → AI decides 1-3 posts + chart recs
  Stage 2 (Writer): Per-post: referenced chapters → prompt.md → evaluate loop

Three-tier fallback:
  1. Two-stage (strategist + writer) — primary
  2. Single-stage (existing keyword extraction + prompt) — if strategist fails
  3. Template (existing _generate_from_template) — if no API

Usage:
    from platforms.xueqiu.generate import generate, generate_multi, generate_to_file
    from engine import MarkdownReportParser

    report = MarkdownReportParser().parse(Path("report.md"))
    result = generate_multi(report)       # XueqiuGenerationResult
    content = generate(report)            # str (first post, backward compat)
    output_path = generate_to_file(report)
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Ensure the project root is importable ──────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.report_schema import ReportData
from engine.config import GEMINI_MODEL, PRODUCTION_URL, get_company_name
from engine.html_utils import save_html, copy_to_clipboard

# ── Paths ──────────────────────────────────────────────────────────────
_PLATFORM_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _PLATFORM_DIR / "config.json"
_PROMPT_PATH = _PLATFORM_DIR / "prompt.md"
_STRATEGIST_PROMPT_PATH = _PLATFORM_DIR / "strategist_prompt.md"
_TEMPLATE_PATH = _PLATFORM_DIR / "template.md"
_ARCHIVE_DIR = _PLATFORM_DIR / "archive"


# ── Result dataclasses ────────────────────────────────────────────────

@dataclass
class XueqiuPost:
    content: str
    post_id: str
    title_hook: str
    recommended_charts: list[dict] = field(default_factory=list)  # [{chart_id, chapter, reason}]


@dataclass
class XueqiuGenerationResult:
    posts: list[XueqiuPost] = field(default_factory=list)
    rationale: str = ""
    strategy_json: dict = field(default_factory=dict)


# ── Config/prompt loaders ─────────────────────────────────────────────

def _load_config() -> dict:
    """Load the platform config.json."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_prompt_template() -> str:
    """Load the Gemini prompt template from prompt.md."""
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _load_strategist_prompt() -> str:
    """Load the strategist prompt from strategist_prompt.md."""
    with open(_STRATEGIST_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ── Report data formatting helpers ─────────────────────────────────────

def _format_key_findings(report: ReportData) -> str:
    """Format key findings as a numbered list."""
    if not report.key_findings:
        return "(No key findings available)"
    lines = []
    for i, finding in enumerate(report.top_findings(8), 1):
        lines.append(f"{i}. {finding}")
    return "\n".join(lines)


def _format_financial_snapshot(report: ReportData) -> str:
    """Format the financial snapshot dict into readable text."""
    snap = report.financial_snapshot
    if not snap:
        return "(No financial data available)"
    lines = []
    label_map = {
        "pe_ttm": "PE TTM",
        "ps_ttm": "PS TTM",
        "roe": "ROE",
        "roic": "ROIC",
        "gross_margin": "Gross Margin",
        "net_margin": "Net Margin",
        "ttm_revenue": "TTM Revenue",
        "fcf": "Free Cash Flow",
        "debt_equity": "Debt/Equity",
    }
    for key, label in label_map.items():
        if key in snap:
            value = snap[key]
            # Add % suffix for margin/return metrics
            if key in ("roe", "roic", "gross_margin", "net_margin"):
                lines.append(f"- {label}: {value}%")
            elif key in ("pe_ttm", "ps_ttm"):
                lines.append(f"- {label}: {value}x")
            else:
                lines.append(f"- {label}: {value}")
    return "\n".join(lines) if lines else "(No financial data available)"


def _format_risk_factors(report: ReportData) -> str:
    """Format risk factors as a bulleted list."""
    if not report.risk_factors:
        return "(No risk factors identified)"
    lines = []
    for risk in report.risk_factors[:5]:
        lines.append(f"- {risk}")
    return "\n".join(lines)


# ── Rich chapter data extraction ──────────────────────────────────────

def _extract_chapter_content(
    report: ReportData, keywords: list[str], max_chars: int = 4000
) -> str:
    """Extract content from the first chapter whose title matches any keyword."""
    for ch in report.chapters:
        title_lower = ch.title.lower()
        for kw in keywords:
            if kw in title_lower:
                content = ch.content_markdown
                # Strip markdown reference tags like [硬数据: ...] [合理推断: ...]
                content = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", content)
                # Strip mermaid blocks
                content = re.sub(r"```mermaid\s*\n.*?```", "", content, flags=re.DOTALL)
                return content[:max_chars]
    return ""


def _extract_multi_chapter_content(
    report: ReportData, keywords: list[str], max_chars: int = 4000
) -> str:
    """Extract and combine content from multiple chapters matching keywords."""
    parts = []
    total = 0
    for ch in report.chapters:
        title_lower = ch.title.lower()
        for kw in keywords:
            if kw in title_lower:
                content = ch.content_markdown
                content = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", content)
                content = re.sub(r"```mermaid\s*\n.*?```", "", content, flags=re.DOTALL)
                available = max_chars - total
                if available <= 200:
                    break
                chunk = content[:available]
                parts.append(f"[{ch.title}]\n{chunk}")
                total += len(chunk)
                break
    return "\n\n".join(parts) if parts else ""


def _extract_core_contradiction(report: ReportData) -> str:
    """Extract core contradiction from exec summary chapter or report field."""
    if report.core_contradiction:
        return report.core_contradiction[:1500]
    # Try to extract from executive summary chapters
    for ch in report.chapters:
        if "执行摘要" in ch.title or "核心结论" in ch.title:
            content = ch.content_markdown
            # Look for core contradiction marker
            for marker in ["核心矛盾", "一句话"]:
                if marker in content:
                    idx = content.index(marker)
                    end = min(idx + 800, len(content))
                    return content[idx:end]
            # Return chapter beginning as fallback
            return content[:1500]
    # Fall back to executive_summary field
    if report.executive_summary:
        return report.executive_summary[:1500]
    return "(Not available)"


def _format_critical_questions(report: ReportData) -> str:
    """Format critical questions from report data or chapter content."""
    if report.critical_questions:
        lines = []
        for cq in report.critical_questions[:8]:
            cq_id = cq.get("id", "")
            question = cq.get("question", "")
            weight = cq.get("weight", "")
            lines.append(f"- {cq_id}: {question} (权重: {weight})")
        return "\n".join(lines)
    # Fallback: extract from chapter
    content = _extract_chapter_content(report, ["关键问题", "cq"], max_chars=2000)
    return content or "(Not available)"


def _clean_chapter_for_template(content: str) -> str:
    """Clean raw chapter markdown into plain text suitable for Xueqiu."""
    # Remove code blocks
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    # Remove reference tags
    content = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", content)
    # Remove markdown headers (### etc) but keep the text
    content = re.sub(r"^#{1,6}\s*", "", content, flags=re.MULTILINE)
    # Remove bold/italic markers (greedy: handle nested **text**)
    content = re.sub(r"\*{2}([^*]*?)\*{2}", r"\1", content)
    content = re.sub(r"\*([^*]*?)\*", r"\1", content)
    # Catch any remaining asterisks used as formatting
    content = re.sub(r"(?<!\w)\*\*(?!\w)", "", content)
    # Remove markdown table lines — convert simple tables to bullet lists
    lines = content.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip table separator lines (|---|---|)
        if re.match(r"^\|[\s:|-]+\|$", stripped):
            continue
        # Convert table data rows to text
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 2:
                cleaned_lines.append("· " + " | ".join(cells[:4]))
            continue
        # Skip inline reference markers
        cleaned_lines.append(line)
    content = "\n".join(cleaned_lines)
    # Remove > blockquote markers
    content = re.sub(r"^>\s*", "", content, flags=re.MULTILINE)
    # Clean up multiple blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content


def _get_reliable_company_name(report: ReportData) -> str:
    """Get reliable company name: prefer config mapping, fall back to parsed."""
    ticker = report.metadata.ticker.upper()
    # Config mapping is authoritative
    mapped = get_company_name(ticker)
    if mapped != ticker:
        return mapped
    # Fall back to parsed name only if it looks like a real name
    parsed = report.metadata.company_name
    if parsed and len(parsed) > 1 and not any(c.isdigit() for c in parsed[:3]):
        return parsed
    return ticker


def _get_metadata_field(report: ReportData, field: str) -> str:
    """Get metadata field, falling back to key_findings if empty."""
    val = getattr(report.metadata, field, "")
    if val:
        return val
    # Try to extract from key findings
    patterns = {
        "market_cap": r"市值[：:]\s*(\$?[\d,.]+[BMT]?)",
        "stock_price": r"股价[基准]*[：:]\s*(\$?[\d,.]+)",
    }
    if field in patterns:
        for finding in report.key_findings:
            m = re.search(patterns[field], finding)
            if m:
                return m.group(1)
    return "(Not available)"


# ── Compliance checks ──────────────────────────────────────────────────

def _check_compliance(content: str, config: dict) -> str:
    """
    Check generated content for forbidden words and ensure the required
    disclaimer is present. Removes forbidden words and appends disclaimer
    if missing.
    """
    compliance = config.get("compliance", {})

    # Remove forbidden words — use context-aware replacements
    _replacements = {
        "买入": "配置", "卖出": "减持", "目标价": "参考价位",
        "低估": "定价偏低", "高估": "定价偏高",
        "overvalued": "richly valued", "undervalued": "attractively valued",
    }
    forbidden = compliance.get("forbidden_words", [])
    for word in forbidden:
        if word in content:
            replacement = _replacements.get(word, "…")
            content = content.replace(word, replacement)

    # Ensure required disclaimer is present
    disclaimer = compliance.get("required_disclaimer", "")
    if disclaimer and disclaimer not in content:
        content = content.rstrip() + "\n\n" + disclaimer

    return content


def _check_length(content: str, config: dict) -> str:
    """
    Ensure content is within the min/max character bounds.
    Truncates if too long (preserving the last paragraph).
    """
    min_chars = config.get("min_chars", 2000)
    max_chars = config.get("max_chars", 5000)

    if len(content) > max_chars:
        # Truncate but keep the last paragraph (usually the disclaimer)
        paragraphs = content.split("\n\n")
        last_paragraph = paragraphs[-1] if paragraphs else ""
        truncated = content[: max_chars - len(last_paragraph) - 10]
        # Cut at last sentence boundary
        last_period = max(
            truncated.rfind("。"),
            truncated.rfind("；"),
            truncated.rfind("\n"),
        )
        if last_period > max_chars // 2:
            truncated = truncated[: last_period + 1]
        content = truncated + "\n\n" + last_paragraph

    return content


# ── Template-based fallback ────────────────────────────────────────────

def _select_best_paragraphs(markdown: str, max_chars: int = 2000) -> str:
    """
    Rank paragraphs by numeric data density and select the top ones.

    Scoring per paragraph:
    - +2 for each number token (e.g. 35%, $1.2B, 10x, 3倍)
    - +1 for comparison words (vs, 而, 但, 相比, 增长, 下降, 增至, 降至)
    - +0.5 for being >100 chars (substantive content)
    - Filtered out: headings, TOC lines, disclaimers, very short lines
    """
    paragraphs = markdown.split("\n\n")
    scored: list[tuple[float, str]] = []

    _comparison_words = ["vs", "而", "但", "相比", "增长", "下降", "增至", "降至",
                         "同比", "环比", "较", "超过", "达到", "从", "提升"]

    for p in paragraphs:
        text = p.strip()
        if len(text) < 30:
            continue
        if text.startswith("#"):
            continue
        if text.startswith("|") and text.endswith("|"):
            continue  # table rows
        if "不构成投资建议" in text or "数据来源" in text:
            continue
        if text.startswith("- [") or text.startswith("* ["):
            continue  # TOC links

        # Strip markdown formatting for cleaner output
        clean = re.sub(r"[#*_`]", "", text)
        clean = re.sub(r"^\s*[-•]\s*", "", clean, flags=re.MULTILINE)

        num_count = len(re.findall(r"[\d,.]+[%$BMKx倍亿万]|\$[\d,.]+[BMK]?", clean))
        has_comparison = sum(1 for w in _comparison_words if w in clean)
        score = num_count * 2 + min(has_comparison, 3) + (0.5 if len(clean) > 100 else 0)

        if score > 0:
            scored.append((score, clean))

    scored.sort(key=lambda x: x[0], reverse=True)

    result_parts: list[str] = []
    total = 0
    for _, para in scored:
        if total + len(para) > max_chars:
            break
        result_parts.append(para)
        total += len(para)

    return "\n\n".join(result_parts)


def _generate_from_template(report: ReportData, config: dict) -> str:
    """
    Generate Xueqiu post using structured chapter content extraction.

    When AI is unavailable, this extracts the most valuable data-dense
    content from report chapters (financial, moat, valuation, scenarios)
    and assembles a structured post.
    """
    ticker = report.metadata.ticker
    compliance = config.get("compliance", {})
    disclaimer = compliance.get("required_disclaimer", "")

    sections: list[str] = []

    # ── Line 1: Report link ────────────────────────────────────────────
    company = _get_reliable_company_name(report)
    cta_template = config.get("cta_template", "")
    if cta_template:
        cta = cta_template.format(ticker_lower=ticker.lower())
        sections.append(f"${company}({ticker})$ {cta}")
    else:
        sections.append(
            f"${company}({ticker})$ "
            f"[完整分析报告链接](https://www.100baggers.club/reports/{ticker.lower()})"
        )

    # ── Core contradiction / executive summary ─────────────────────────
    core = _extract_core_contradiction(report)
    if core and core != "(Not available)":
        core = _clean_chapter_for_template(core)
        if len(core.strip()) > 50:
            sections.append(core.strip())

    # ── Body: extract key chapter content with separators ──────────────
    chapter_configs = [
        (["财务全景", "财务深挖", "五年趋势"], 1200),
        (["护城河", "竞争"], 1000),
        (["估值", "sotp", "dcf"], 800),
        (["情景", "三情景", "概率模型"], 600),
    ]

    for keywords, max_chars in chapter_configs:
        content = _extract_chapter_content(report, keywords, max_chars)
        if content:
            content = _clean_chapter_for_template(content)
            if len(content.strip()) > 100:
                sections.append("———\n\n" + content.strip())

    # ── Fallback: data-dense paragraphs from raw markdown ──────────────
    if len(sections) <= 2:
        source = report.raw_markdown or ""
        if not source and report.executive_summary:
            source = report.executive_summary
        best = _select_best_paragraphs(source, max_chars=2000)
        if best:
            sections.append(best)
        elif report.key_findings:
            for finding in report.top_findings(5):
                clean = re.sub(r"[#*_`]", "", finding[:400])
                sections.append(clean)

    # ── Disclaimer ─────────────────────────────────────────────────────
    if disclaimer:
        sections.append(disclaimer)

    content = "\n\n".join(sections)
    print(f"[xueqiu/generate] Template-based generation ({len(content)} chars)")
    return content


# ══════════════════════════════════════════════════════════════════════
# TWO-STAGE PIPELINE
# ══════════════════════════════════════════════════════════════════════

# ── Preprocessing ─────────────────────────────────────────────────────

def _preprocess_markdown(raw: str) -> str:
    """Strip noise from raw markdown to fit in Gemini's context window.

    Removes: [DM-xxx] tags, mermaid/code blocks, appendix sections,
    table separator lines, compresses whitespace. Hard cap at 800K chars.
    """
    text = raw

    # Strip [DM-xxx] reference tags (various formats: DM-FIN-001, DM-P4-01, DM-P3A-01)
    text = re.sub(r"\[DM-[^\]]+\]", "", text)

    # Strip reference tags like [硬数据: ...] [合理推断: ...]
    text = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", text)

    # Strip mermaid code blocks
    text = re.sub(r"```mermaid\s*\n.*?```", "", text, flags=re.DOTALL)

    # Strip other code blocks (keep content of plain text blocks)
    text = re.sub(r"```(?:graph|flowchart|dot|plantuml)\s*\n.*?```", "", text, flags=re.DOTALL)

    # Strip ASCII art (lines of dashes/pipes)
    text = re.sub(r"(?m)^[│├└┌┐┘┤┬┴┼─]{3,}.*$", "", text)

    # Compress table separator lines (|---|---|) to a single marker
    text = re.sub(r"^\|[\s:|-]+\|$", "|---|", text, flags=re.MULTILINE)

    # Compress runs of 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Hard cap with smart truncation from end
    if len(text) > 800_000:
        # Try to cut at a chapter boundary
        cut_point = text.rfind("\n## ", 0, 800_000)
        if cut_point > 600_000:
            text = text[:cut_point] + "\n\n[…报告后续章节已截断]"
        else:
            text = text[:800_000] + "\n\n[…已截断]"

    return text


# ── Strategist stage ──────────────────────────────────────────────────

def _call_strategist(
    report: ReportData, chart_catalog_text: str
) -> Optional[dict]:
    """Call Gemini with the full report to get a post strategy.

    Returns the parsed strategy JSON dict, or None on failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        return None

    # Preprocess the full markdown
    full_text = _preprocess_markdown(report.raw_markdown)
    if len(full_text) < 500:
        print("[xueqiu/generate] Preprocessed markdown too short for strategist")
        return None

    strategist_template = _load_strategist_prompt()
    prompt = strategist_template.format(
        ticker=report.metadata.ticker.upper(),
        company_name=_get_reliable_company_name(report),
        full_report=full_text,
        chart_catalog=chart_catalog_text or "(No HTML report / no charts found)",
    )

    print(f"[xueqiu/generate] Calling strategist ({len(prompt)} chars prompt, "
          f"~{len(prompt) // 4} tokens est.)")

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        raw = response.text.strip()
    except Exception as e:
        print(f"[xueqiu/generate] Strategist call failed: {e}")
        return None

    # Parse JSON — strip markdown fences if present
    return _parse_strategy_json(raw)


def _parse_strategy_json(raw: str) -> Optional[dict]:
    """Robustly parse JSON from strategist response."""
    text = raw.strip()

    # Strip markdown code fences
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    text = text.strip()

    try:
        result = json.loads(text)
        if "posts" in result and isinstance(result["posts"], list):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: extract the first JSON object
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        try:
            result = json.loads(match.group())
            if "posts" in result and isinstance(result["posts"], list):
                return result
        except json.JSONDecodeError:
            pass

    print("[xueqiu/generate] Failed to parse strategist JSON response")
    return None


# ── Chapter extraction for writer ─────────────────────────────────────

def _extract_chapters_for_post(
    report: ReportData, chapter_refs: list[int]
) -> str:
    """Extract full content_markdown for the chapters referenced by the strategist.

    chapter_refs are 1-based chapter numbers. Tries multiple title patterns:
    - HTML format: "第N章：..." (e.g. "第2章：财务全景")
    - Markdown format: "ChN:" (e.g. "Ch2: 财务全景")
    - Fallback: by list index
    """
    parts = []
    for ref in chapter_refs:
        found = False
        # Try matching "第{ref}章" or "Ch{ref}:" in chapter titles
        targets = [f"第{ref}章", f"Ch{ref}:", f"Ch{ref}："]
        for ch in report.chapters:
            if any(t in ch.title for t in targets):
                content = ch.content_markdown
                content = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", content)
                content = re.sub(r"```mermaid\s*\n.*?```", "", content, flags=re.DOTALL)
                parts.append(f"=== {ch.title} ===\n\n{content}")
                found = True
                break

        if not found:
            # Also try "N. " prefix (some markdown reports use "1. 异常狩猎")
            prefix = f"{ref}. "
            for ch in report.chapters:
                if ch.title.startswith(prefix):
                    content = ch.content_markdown
                    content = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", content)
                    content = re.sub(r"```mermaid\s*\n.*?```", "", content, flags=re.DOTALL)
                    parts.append(f"=== {ch.title} ===\n\n{content}")
                    found = True
                    break

        if not found:
            # Last resort: by index (0-based)
            idx = ref - 1
            if 0 <= idx < len(report.chapters):
                ch = report.chapters[idx]
                content = ch.content_markdown
                content = re.sub(r"\[(?:硬数据|合理推断|主观判断)[^\]]*\]", "", content)
                content = re.sub(r"```mermaid\s*\n.*?```", "", content, flags=re.DOTALL)
                parts.append(f"=== {ch.title} ===\n\n{content}")

    return "\n\n".join(parts)


# ── Writer stage ──────────────────────────────────────────────────────

def _build_strategist_directives(post_plan: dict) -> str:
    """Build the strategist directives block for the writer prompt."""
    thesis = post_plan.get("thesis", "")
    hook = post_plan.get("title_hook", "")
    data_points = post_plan.get("key_data_points", [])

    parts = []
    if thesis:
        parts.append(f"主题：{thesis}")
    if hook:
        parts.append(f"开头钩子：{hook}")
    if data_points:
        points_text = "\n".join(f"  - {dp}" for dp in data_points)
        parts.append(f"核心数据点：\n{points_text}")

    return "\n".join(parts) if parts else "(无策略师指示 — 使用默认模式)"


def _call_writer_for_post(
    report: ReportData,
    post_plan: dict,
    chapter_content: str,
    config: dict,
    rewrite_instructions: str = "",
) -> Optional[str]:
    """Generate a single post using the writer prompt with strategist directives."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        return None

    prompt_template = _load_prompt_template()

    # Build strategist directives
    directives = _build_strategist_directives(post_plan)

    # Add the referenced chapter content as the deep dive sections
    # The strategist-selected chapters replace the keyword-extracted sections
    directive_block = (
        f"{directives}\n\n"
        f"以下是策略师选定的章节完整内容（不是全文节选，是完整章节）：\n\n"
        f"{chapter_content}"
    )

    prompt = prompt_template.format(
        ticker=report.metadata.ticker,
        ticker_lower=report.metadata.ticker.lower(),
        company_name=_get_reliable_company_name(report),
        market_cap=_get_metadata_field(report, "market_cap"),
        stock_price=_get_metadata_field(report, "stock_price"),
        core_contradiction=_extract_core_contradiction(report),
        key_findings=_format_key_findings(report),
        financial_snapshot=_format_financial_snapshot(report),
        critical_questions=_format_critical_questions(report),
        strategist_directives=directive_block,
        financial_deep_dive="(见策略师选定章节)",
        moat_analysis="(见策略师选定章节)",
        valuation_analysis="(见策略师选定章节)",
        scenario_analysis="(见策略师选定章节)",
    )

    if rewrite_instructions:
        prompt = (
            f"⚠️ REWRITE REQUIRED — your previous output was rejected.\n"
            f"Issues found: {rewrite_instructions}\n"
            f"Fix ALL issues listed above. Do NOT repeat the same mistakes.\n\n"
            + prompt
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        content = response.text.strip()

        from engine.content_filter import clean_generated_content
        content = clean_generated_content(content)

        if len(content) < 500:
            print(f"[xueqiu/generate] Writer output too short ({len(content)} chars)")
            return None

        return content
    except Exception as e:
        print(f"[xueqiu/generate] Writer call failed: {e}")
        return None


def _write_post_with_eval_loop(
    report: ReportData,
    post_plan: dict,
    chapter_content: str,
    config: dict,
    max_attempts: int = 5,
) -> Optional[str]:
    """Write a single post with evaluate→rewrite loop."""
    ticker = report.metadata.ticker.upper()
    post_id = post_plan.get("post_id", "post")

    min_chars = config.get("min_chars", 5000)
    rewrite_instructions = ""
    for attempt in range(1, max_attempts + 1):
        content = _call_writer_for_post(
            report, post_plan, chapter_content, config, rewrite_instructions,
        )
        if content is None:
            return None

        # Min-length enforcement before evaluator
        if len(content) < min_chars:
            gap = min_chars - len(content)
            print(f"[xueqiu/generate] {post_id} attempt {attempt}: TOO SHORT "
                  f"({len(content)} chars < {min_chars}, need +{gap})")
            rewrite_instructions = (
                f"严重不足！内容仅{len(content)}字，最低要求{min_chars}字，还差{gap}字。"
                f"你必须写出至少{min_chars}字的完整帖子。具体方法："
                f"1) 每个核心论点用3-5句话展开推导过程，不要只给结论；"
                f"2) 每个数据点都加对比(同比/环比/vs竞争对手/vs市场预期)；"
                f"3) 增加2-3个段落深入分析报告中的关键章节数据；"
                f"4) 估值部分展示完整计算过程(隐含CAGR、DCF假设拆解)。"
            )
            continue

        # Evaluate
        from engine.evaluator import evaluate, flatten_content
        eval_result = evaluate(
            flatten_content(content, "xueqiu"), "xueqiu", ticker
        )

        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            print(f"[xueqiu/generate] {post_id} attempt {attempt}: PASS "
                  f"(score {total_score}/15, {len(content)} chars)")
            content = _check_compliance(content, config)
            content = _check_length(content, config)
            return content

        print(f"[xueqiu/generate] {post_id} attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

    return None


# ── Main two-stage entry point ────────────────────────────────────────

def generate_multi(report: ReportData, max_attempts: int = 3) -> Optional[XueqiuGenerationResult]:
    """Two-stage pipeline: strategist → writer for 1-3 posts.

    Returns XueqiuGenerationResult or None if the two-stage pipeline fails.
    """
    config = _load_config()

    # Build chart catalog
    chart_catalog_text = ""
    try:
        from engine.chart_catalog import build_chart_catalog, format_catalog_for_prompt
        catalog = build_chart_catalog(report.metadata.ticker.lower())
        if catalog:
            chart_catalog_text = format_catalog_for_prompt(catalog)
            print(f"[xueqiu/generate] Chart catalog: {len(catalog)} charts found")
    except Exception as e:
        print(f"[xueqiu/generate] Chart catalog build failed: {e}")

    # Stage 1: Strategist
    strategy = _call_strategist(report, chart_catalog_text)
    if not strategy:
        return None

    posts_plan = strategy.get("posts", [])
    if not posts_plan:
        print("[xueqiu/generate] Strategist returned no posts")
        return None

    rationale = strategy.get("rationale", "")
    print(f"[xueqiu/generate] Strategist: {len(posts_plan)} post(s) planned — {rationale}")

    # Stage 2: Writer for each post
    result = XueqiuGenerationResult(
        rationale=rationale,
        strategy_json=strategy,
    )

    for post_plan in posts_plan:
        post_id = post_plan.get("post_id", f"post{len(result.posts) + 1}")
        chapter_refs = post_plan.get("chapter_refs", [])
        chapter_content = _extract_chapters_for_post(report, chapter_refs)

        if not chapter_content:
            print(f"[xueqiu/generate] No chapter content for {post_id}, "
                  f"refs={chapter_refs}")
            continue

        print(f"[xueqiu/generate] Writing {post_id} "
              f"({len(chapter_refs)} chapters, {len(chapter_content)} chars)")

        content = _write_post_with_eval_loop(
            report, post_plan, chapter_content, config, max_attempts,
        )
        if content is None:
            print(f"[xueqiu/generate] {post_id} failed after {max_attempts} attempts")
            continue

        result.posts.append(XueqiuPost(
            content=content,
            post_id=post_id,
            title_hook=post_plan.get("title_hook", ""),
            recommended_charts=post_plan.get("recommended_charts", []),
        ))

    if not result.posts:
        print("[xueqiu/generate] Two-stage pipeline produced no posts")
        return None

    return result


# ── Single-stage (existing) ───────────────────────────────────────────

def _generate_with_ai_and_feedback(
    report: ReportData, config: dict, rewrite_instructions: str = ""
) -> Optional[str]:
    """Generate with optional rewrite instructions prepended to the prompt."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        return None

    prompt_template = _load_prompt_template()

    # Extract rich chapter-based data
    financial_deep = _extract_multi_chapter_content(
        report, ["财务全景", "财务深挖", "财务趋势", "五年趋势"], max_chars=6000
    )
    moat_analysis = _extract_multi_chapter_content(
        report, ["护城河", "竞争"], max_chars=6000
    )
    valuation_analysis = _extract_multi_chapter_content(
        report, ["估值", "dcf", "sotp", "reverse dcf", "cisco类比"], max_chars=6000
    )
    scenario_analysis = _extract_multi_chapter_content(
        report, ["情景", "概率模型", "三情景", "风险", "红队", "承重墙"], max_chars=5000
    )

    prompt = prompt_template.format(
        ticker=report.metadata.ticker,
        ticker_lower=report.metadata.ticker.lower(),
        company_name=_get_reliable_company_name(report),
        market_cap=_get_metadata_field(report, "market_cap"),
        stock_price=_get_metadata_field(report, "stock_price"),
        core_contradiction=_extract_core_contradiction(report),
        key_findings=_format_key_findings(report),
        financial_snapshot=_format_financial_snapshot(report),
        critical_questions=_format_critical_questions(report),
        strategist_directives="(无策略师指示 — 使用默认模式)",
        financial_deep_dive=financial_deep or "(Not available)",
        moat_analysis=moat_analysis or "(Not available)",
        valuation_analysis=valuation_analysis or "(Not available)",
        scenario_analysis=scenario_analysis or "(Not available)",
    )

    if rewrite_instructions:
        prompt = (
            f"⚠️ REWRITE REQUIRED — your previous output was rejected.\n"
            f"Issues found: {rewrite_instructions}\n"
            f"Fix ALL issues listed above. Do NOT repeat the same mistakes.\n\n"
            + prompt
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        content = response.text.strip()

        from engine.content_filter import clean_generated_content
        content = clean_generated_content(content)

        if len(content) < 500:
            print(f"[xueqiu/generate] AI output too short ({len(content)} chars)")
            return None

        return content
    except Exception as e:
        print(f"[xueqiu/generate] AI generation failed: {e}")
        return None


# ── Public API ─────────────────────────────────────────────────────────

def _generate_single_or_template(report: ReportData, max_attempts: int = 5) -> str:
    """Run single-stage pipeline with template fallback (skips two-stage)."""
    config = _load_config()
    ticker = report.metadata.ticker.upper()

    min_chars = config.get("min_chars", 5000)
    rewrite_instructions = ""
    for attempt in range(1, max_attempts + 1):
        content = _generate_with_ai_and_feedback(report, config, rewrite_instructions)
        if content is None:
            break

        # Min-length enforcement before evaluator
        if len(content) < min_chars:
            gap = min_chars - len(content)
            print(f"[xueqiu/generate] Single-stage attempt {attempt}: TOO SHORT "
                  f"({len(content)} chars < {min_chars}, need +{gap})")
            rewrite_instructions = (
                f"严重不足！内容仅{len(content)}字，最低要求{min_chars}字，还差{gap}字。"
                f"你必须写出至少{min_chars}字的完整帖子。具体方法："
                f"1) 每个核心论点用3-5句话展开推导过程，不要只给结论；"
                f"2) 每个数据点都加对比(同比/环比/vs竞争对手/vs市场预期)；"
                f"3) 增加2-3个段落深入分析报告中的关键章节数据；"
                f"4) 估值部分展示完整计算过程(隐含CAGR、DCF假设拆解)。"
            )
            continue

        from engine.evaluator import evaluate, flatten_content
        eval_result = evaluate(
            flatten_content(content, "xueqiu"), "xueqiu", ticker
        )

        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            print(f"[xueqiu/generate] Single-stage attempt {attempt}: PASS (score {total_score}/15, {len(content)} chars)")
            content = _check_compliance(content, config)
            content = _check_length(content, config)
            return content

        print(f"[xueqiu/generate] Single-stage attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

    # Template fallback
    print(f"[xueqiu/generate] All AI generation failed, using template for {ticker}")
    content = _generate_from_template(report, config)
    content = _check_compliance(content, config)
    content = _check_length(content, config)
    return content


def generate(report: ReportData, max_attempts: int = 5) -> str:
    """
    Generate a Xueqiu long-form post from a ReportData object.

    Three-tier fallback:
    1. Two-stage (strategist + writer) — returns first post
    2. Single-stage (keyword extraction + prompt + evaluate loop)
    3. Template (no API needed)

    Args:
        report: Parsed report data from the engine.
        max_attempts: Maximum generation+evaluation rounds (default 3).

    Returns:
        The generated post content as a plain-text string, ready to publish.
    """
    ticker = report.metadata.ticker.upper()

    # Tier 1: Two-stage pipeline
    print(f"[xueqiu/generate] Trying two-stage pipeline for {ticker}")
    try:
        result = generate_multi(report, max_attempts)
        if result and result.posts:
            print(f"[xueqiu/generate] Two-stage: {len(result.posts)} post(s) generated")
            return result.posts[0].content
    except Exception as e:
        print(f"[xueqiu/generate] Two-stage pipeline failed: {e}")

    # Tier 2+3: Single-stage with template fallback
    print(f"[xueqiu/generate] Falling back to single-stage for {ticker}")
    return _generate_single_or_template(report, max_attempts)


def _to_crlf(text: str) -> str:
    """Convert \\n to \\r\\n so copy-paste into web editors preserves line breaks."""
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def _save_html(text_content: str, html_path: Path, chart_footer: str = "") -> None:
    """Save post as HTML file for Xueqiu publishing. Delegates to engine.html_utils."""
    save_html(text_content, html_path, chart_footer)
    print(f"[xueqiu/generate] Saved {html_path.name}")


def generate_to_file(report: ReportData, output_dir: Optional[Path] = None) -> Path:
    """
    Generate Xueqiu posts and save to the archive directory.

    Two-stage output: saves post1.txt, post2.txt, etc. + strategy.json
    with chart recommendations. Also captures chart screenshots.

    Falls back to single file if two-stage fails.

    Returns:
        Path to the first post file.
    """
    ticker = report.metadata.ticker.upper()
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Determine output directory
    if output_dir is None:
        output_dir = _ARCHIVE_DIR / ticker.lower()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Try two-stage first
    result = None
    try:
        result = generate_multi(report)
    except Exception as e:
        print(f"[xueqiu/generate] Two-stage failed in generate_to_file: {e}")

    if result and result.posts:
        first_path = None

        # Save each post as HTML
        for i, post in enumerate(result.posts, 1):
            suffix = f"-post{i}" if len(result.posts) > 1 else ""
            filename = f"{ticker}-xueqiu-{date_str}{suffix}.html"
            filepath = output_dir / filename

            # Build chart footer text
            chart_footer = ""
            if post.recommended_charts:
                footer_lines = ["配图建议:"]
                for j, chart in enumerate(post.recommended_charts, 1):
                    chart_id = chart.get("chart_id", "")
                    chapter = chart.get("chapter", "")
                    reason = chart.get("reason", "")
                    footer_lines.append(f"图{j}: {chart_id} ({chapter}) — {reason}")
                chart_footer = "\n".join(footer_lines)

            _save_html(post.content, filepath, chart_footer)

            if first_path is None:
                first_path = filepath

        # Save strategy JSON
        strategy_path = output_dir / f"{ticker}-xueqiu-{date_str}-strategy.json"
        strategy_path.write_text(
            json.dumps(result.strategy_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[xueqiu/generate] Saved {strategy_path.name}")

        # Capture chart screenshots
        all_chart_ids = []
        for post in result.posts:
            for chart in post.recommended_charts:
                cid = chart.get("chart_id", "")
                if cid and cid not in all_chart_ids:
                    all_chart_ids.append(cid)

        if all_chart_ids:
            try:
                from engine.chart_screenshot import capture_chart_by_ids
                screenshots = capture_chart_by_ids(
                    ticker.lower(), all_chart_ids, output_dir,
                )
                for chart_id, path in screenshots.items():
                    # Rename to dated format
                    dated_name = f"{ticker}-xueqiu-{date_str}-{chart_id}.jpg"
                    dated_path = output_dir / dated_name
                    if path != dated_path:
                        path.rename(dated_path)
                    print(f"[xueqiu/generate] Chart screenshot: {dated_name}")
            except Exception as e:
                print(f"[xueqiu/generate] Chart screenshot capture failed: {e}")

        return first_path

    # Fallback: single-stage or template (skip two-stage to avoid double call)
    content = _generate_single_or_template(report)
    filename = f"{ticker}-xueqiu-{date_str}.html"
    output_path = output_dir / filename
    _save_html(content, output_path)
    return output_path


# ── CLI entry point ────────────────────────────────────────────────────

def _copy_to_clipboard(html_path: Path) -> bool:
    """Copy HTML to macOS clipboard as rich text. Delegates to engine.html_utils."""
    return copy_to_clipboard(html_path)


def _cli() -> None:
    """Simple CLI for testing: python generate.py <ticker> [--save] [--single] [--copy]"""
    import argparse

    parser = argparse.ArgumentParser(description="Generate Xueqiu post from a 100Baggers report")
    parser.add_argument("ticker", help="Stock ticker (e.g. TSLA, AAPL)")
    parser.add_argument("--save", action="store_true", help="Save output to archive/")
    parser.add_argument("--single", action="store_true", help="Force single-stage (skip strategist)")
    parser.add_argument("--copy", action="store_true", help="Copy result to clipboard (macOS, for pasting into Xueqiu)")
    args = parser.parse_args()

    from engine.config import find_markdown_report, find_html_report
    from engine.markdown_parser import MarkdownReportParser
    from engine.report_parser import HTMLReportParser

    ticker = args.ticker.lower()

    # Try markdown first, then HTML
    md_path = find_markdown_report(ticker)
    if md_path:
        report = MarkdownReportParser().parse(md_path)
        print(f"[xueqiu/generate] Parsed markdown report: {md_path.name}")
    else:
        html_path = find_html_report(ticker)
        if html_path:
            report = HTMLReportParser().parse(html_path)
            print(f"[xueqiu/generate] Parsed HTML report: {html_path.name}")
        else:
            print(f"[xueqiu/generate] No report found for ticker: {ticker}")
            sys.exit(1)

    if args.save:
        output_path = generate_to_file(report)
        print(f"\nSaved to: {output_path}")
        if args.copy and output_path.suffix == ".html":
            if _copy_to_clipboard(output_path):
                print("Copied to clipboard — paste directly into Xueqiu editor")
    elif args.single:
        # Force single-stage
        config = _load_config()
        content = _generate_with_ai_and_feedback(report, config)
        if content:
            print("\n" + "=" * 60)
            print(content)
            print("=" * 60)
            print(f"\nTotal characters: {len(content)}")
        else:
            print("Single-stage generation failed")
    else:
        content = generate(report)
        print("\n" + "=" * 60)
        print(content)
        print("=" * 60)
        print(f"\nTotal characters: {len(content)}")


if __name__ == "__main__":
    _cli()
