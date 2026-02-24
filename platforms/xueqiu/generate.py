#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xueqiu (雪球) long-form post generator.

Takes a ReportData object from the engine, uses Gemini AI to produce a
2000-5000 character Chinese post suitable for Xueqiu's professional
investor audience. Falls back to template-based generation when AI is
unavailable.

Usage:
    from platforms.xueqiu.generate import generate, generate_to_file
    from engine import MarkdownReportParser

    report = MarkdownReportParser().parse(Path("report.md"))
    content = generate(report)
    output_path = generate_to_file(report, Path("output/"))
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Ensure the project root is importable ──────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.report_schema import ReportData
from engine.config import GEMINI_MODEL, PRODUCTION_URL

# ── Paths ──────────────────────────────────────────────────────────────
_PLATFORM_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _PLATFORM_DIR / "config.json"
_PROMPT_PATH = _PLATFORM_DIR / "prompt.md"
_TEMPLATE_PATH = _PLATFORM_DIR / "template.md"
_ARCHIVE_DIR = _PLATFORM_DIR / "archive"


def _load_config() -> dict:
    """Load the platform config.json."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_prompt_template() -> str:
    """Load the Gemini prompt template from prompt.md."""
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ── Report data formatting helpers ─────────────────────────────────────

def _format_key_findings(report: ReportData) -> str:
    """Format key findings as a numbered list."""
    if not report.key_findings:
        return "(No key findings available)"
    lines = []
    for i, finding in enumerate(report.top_findings(5), 1):
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


# ── Compliance checks ──────────────────────────────────────────────────

def _check_compliance(content: str, config: dict) -> str:
    """
    Check generated content for forbidden words and ensure the required
    disclaimer is present. Removes forbidden words and appends disclaimer
    if missing.
    """
    compliance = config.get("compliance", {})

    # Remove forbidden words
    forbidden = compliance.get("forbidden_words", [])
    for word in forbidden:
        if word in content:
            # Replace with ellipsis to preserve sentence structure
            content = content.replace(word, "...")

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
    Generate Xueqiu post using data-dense paragraph selection.

    Format matches live example posts:
    - Line 1: $TICKER$ 完整分析报告链接: URL
    - Body: Top data-dense paragraphs from the report
    - Footer: Disclaimer only
    """
    ticker = report.metadata.ticker
    compliance = config.get("compliance", {})
    disclaimer = compliance.get("required_disclaimer", "")

    sections: list[str] = []

    # ── Line 1: Report link ────────────────────────────────────────────
    cta_template = config.get("cta_template", "")
    if cta_template:
        cta = cta_template.format(ticker_lower=ticker.lower())
        sections.append(f"${ticker}$ {cta}")
    else:
        sections.append(f"${ticker}$ 完整分析报告: https://www.100baggers.club/reports/{ticker.lower()}")

    # ── Body: best paragraphs from raw report ──────────────────────────
    source = report.raw_markdown or ""
    if not source and report.executive_summary:
        source = report.executive_summary
    best = _select_best_paragraphs(source, max_chars=2000)
    if best:
        sections.append(best)
    else:
        # Fallback: use executive summary + key findings
        if report.executive_summary:
            clean_summary = re.sub(r"[#*_`]", "", report.executive_summary[:1000])
            sections.append(clean_summary)
        if report.key_findings:
            for finding in report.top_findings(3):
                clean = re.sub(r"[#*_`]", "", finding[:400])
                sections.append(clean)

    # ── Disclaimer ─────────────────────────────────────────────────────
    if disclaimer:
        sections.append(disclaimer)

    content = "\n\n".join(sections)
    print(f"[xueqiu/generate] Template-based generation ({len(content)} chars)")
    return content


# ── Public API ─────────────────────────────────────────────────────────

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
    prompt = prompt_template.format(
        ticker=report.metadata.ticker,
        ticker_lower=report.metadata.ticker.lower(),
        company_name=report.metadata.company_name,
        executive_summary=report.executive_summary[:8000] or "(Not available)",
        core_contradiction=report.core_contradiction[:1000] or "(Not available)",
        key_findings=_format_key_findings(report),
        financial_snapshot=_format_financial_snapshot(report),
        risk_factors=_format_risk_factors(report),
        bull_case=report.bull_case[:1000] or "(Not available)",
        bear_case=report.bear_case[:1000] or "(Not available)",
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


def generate(report: ReportData, max_attempts: int = 3) -> str:
    """
    Generate a Xueqiu long-form post from a ReportData object.

    Uses an evaluate→rewrite loop: generates content, evaluates it with
    Gemini, and regenerates with feedback if quality issues are found.
    Falls back to template if AI is unavailable.

    Args:
        report: Parsed report data from the engine.
        max_attempts: Maximum generation+evaluation rounds (default 3).

    Returns:
        The generated post content as a plain-text string, ready to publish.
    """
    config = _load_config()
    ticker = report.metadata.ticker.upper()

    rewrite_instructions = ""
    for attempt in range(1, max_attempts + 1):
        content = _generate_with_ai_and_feedback(report, config, rewrite_instructions)
        if content is None:
            break  # AI unavailable, fall back to template

        # Evaluate with Gemini
        from engine.evaluator import evaluate, flatten_content
        eval_result = evaluate(
            flatten_content(content, "xueqiu"), "xueqiu", ticker
        )

        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            print(f"[xueqiu/generate] Attempt {attempt}: PASS (score {total_score}/15, {len(content)} chars)")
            content = _check_compliance(content, config)
            content = _check_length(content, config)
            return content

        # Failed — log and prepare rewrite
        print(f"[xueqiu/generate] Attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

    # All AI attempts failed or exhausted — fall back to template
    print(f"[xueqiu/generate] AI generation failed after {max_attempts} attempts, using template")
    content = _generate_from_template(report, config)
    content = _check_compliance(content, config)
    content = _check_length(content, config)
    return content


def generate_to_file(report: ReportData, output_dir: Optional[Path] = None) -> Path:
    """
    Generate a Xueqiu post and save it to the archive directory.

    The file is saved at: archive/{ticker}/{ticker}-xueqiu-{date}.txt

    Args:
        report: Parsed report data from the engine.
        output_dir: Override output directory. Defaults to platform archive dir.

    Returns:
        Path to the saved file.
    """
    ticker = report.metadata.ticker.upper()
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Determine output directory
    if output_dir is None:
        output_dir = _ARCHIVE_DIR / ticker.lower()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate content
    content = generate(report)

    # Save to file
    filename = f"{ticker}-xueqiu-{date_str}.txt"
    output_path = output_dir / filename
    output_path.write_text(content, encoding="utf-8")

    print(f"[xueqiu/generate] Saved to {output_path}")
    return output_path


# ── CLI entry point ────────────────────────────────────────────────────

def _cli() -> None:
    """Simple CLI for testing: python generate.py <ticker>"""
    import argparse

    parser = argparse.ArgumentParser(description="Generate Xueqiu post from a 100Baggers report")
    parser.add_argument("ticker", help="Stock ticker (e.g. TSLA, AAPL)")
    parser.add_argument("--save", action="store_true", help="Save output to archive/")
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
    else:
        content = generate(report)
        print("\n" + "=" * 60)
        print(content)
        print("=" * 60)
        print(f"\nTotal characters: {len(content)}")


if __name__ == "__main__":
    _cli()
