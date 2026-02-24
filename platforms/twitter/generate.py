#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter/X long-form post generator for 100Baggers deep research reports.

Generates a single long-form post (300-500 words) using Gemini AI.

Usage:
    from platforms.twitter.generate import generate, generate_to_file
    from engine.report_schema import ReportData

    post = generate(report)
    path = generate_to_file(report, output_dir)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Resolve project root so engine imports work ─────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.report_schema import ReportData
from engine.config import (
    GEMINI_MODEL,
    REPORT_URL_TEMPLATE,
    find_english_markdown,
)

# ── Paths ───────────────────────────────────────────────────────────────
_PLATFORM_DIR = Path(__file__).resolve().parent
_PROMPT_PATH = _PLATFORM_DIR / "prompt.md"
_CONFIG_PATH = _PLATFORM_DIR / "config.json"
_ARCHIVE_DIR = _PLATFORM_DIR / "archive"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_prompt() -> str:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ── Formatting helpers ──────────────────────────────────────────────────

def _format_key_findings(findings: list[str], max_items: int = 8) -> str:
    if not findings:
        return "(none available)"
    return "\n".join(f"{i}. {f}" for i, f in enumerate(findings[:max_items], 1))


def _format_financial_snapshot(snapshot: dict) -> str:
    if not snapshot:
        return "(none available)"
    label_map = {
        "pe_ttm": "PE TTM", "ps_ttm": "PS TTM", "roe": "ROE",
        "roic": "ROIC", "gross_margin": "Gross Margin",
        "net_margin": "Net Margin", "operating_margin": "Operating Margin",
        "ttm_revenue": "TTM Revenue", "fcf": "Free Cash Flow",
        "fcf_yield": "FCF Yield", "dividend_yield": "Dividend Yield",
        "debt_equity": "Debt/Equity", "ev_ebitda": "EV/EBITDA",
        "current_ratio": "Current Ratio",
    }
    lines = []
    for key, value in snapshot.items():
        label = label_map.get(key, key)
        lines.append(f"- {label}: {value}")
    return "\n".join(lines) if lines else "(none available)"


def _format_risk_factors(risks: list[str], max_items: int = 6) -> str:
    if not risks:
        return "(none available)"
    return "\n".join(f"- {r}" for r in risks[:max_items])


def _build_prompt(report: ReportData) -> str:
    template = _load_prompt()
    ticker = report.metadata.ticker.upper()
    company_name = report.metadata.company_name or ticker

    filled = template.replace("{ticker}", ticker)
    filled = filled.replace("{ticker_lower}", ticker.lower())
    filled = filled.replace("{company_name}", company_name)
    filled = filled.replace(
        "{executive_summary}",
        report.executive_summary[:2000] if report.executive_summary else "(none available)",
    )
    filled = filled.replace("{key_findings}", _format_key_findings(report.key_findings))
    filled = filled.replace("{financial_snapshot}", _format_financial_snapshot(report.financial_snapshot))
    filled = filled.replace("{risk_factors}", _format_risk_factors(report.risk_factors))
    return filled


# ── Compliance check ────────────────────────────────────────────────────

def _compliance_check(text: str) -> list[str]:
    config = _load_config()
    forbidden = config.get("compliance", {}).get("forbidden_words", [])
    violations = []
    text_lower = text.lower()
    for word in forbidden:
        if word.lower() in text_lower:
            violations.append(f"Forbidden word found: '{word}'")
    return violations


# ── Core generation ─────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    text = response.text.strip()

    # Post-generation filter: strip Mermaid, code blocks, price targets
    from engine.content_filter import clean_generated_content
    text = clean_generated_content(text)

    return text


def _postprocess(raw_output: str, ticker: str) -> str:
    """Clean up and ensure CTA link is present."""
    post = raw_output.strip().strip('"\'')
    cta_url = REPORT_URL_TEMPLATE.format(ticker=ticker.lower())
    if cta_url.lower() not in post.lower() and "100baggers.club" not in post.lower():
        post += f"\n\nData: {cta_url}"
    return post


def generate(report: ReportData, max_attempts: int = 3) -> str:
    """
    Generate a long-form Twitter/X post from a ReportData object.

    Uses evaluate->rewrite loop: generates, evaluates with Gemini,
    regenerates with feedback if quality issues are found.
    """
    config = _load_config()
    ticker = report.metadata.ticker.upper()

    # If an English report exists, enrich raw_markdown
    en_md_path = find_english_markdown(ticker.lower())
    if en_md_path and en_md_path.exists():
        en_text = en_md_path.read_text(encoding="utf-8")
        if len(en_text) > len(report.raw_markdown):
            report.raw_markdown = en_text

    rewrite_instructions = ""
    result = None

    for attempt in range(1, max_attempts + 1):
        prompt = _build_prompt(report)
        if rewrite_instructions:
            prompt = (
                f"REWRITE REQUIRED — your previous output was rejected.\n"
                f"Issues found: {rewrite_instructions}\n"
                f"Fix ALL issues. Do NOT repeat the same mistakes.\n\n"
                + prompt
            )

        try:
            raw_output = _call_gemini(prompt)
        except Exception as exc:
            print(f"[twitter/generate] Attempt {attempt} failed: {exc}")
            break

        result = _postprocess(raw_output, ticker)

        # Check word count
        word_count = len(result.split())
        min_words = config.get("post_min_words", 300)
        max_words = config.get("post_max_words", 500)
        if word_count < min_words:
            print(f"[twitter/generate] Warning: post is short ({word_count} words, min {min_words})")
        elif word_count > max_words:
            print(f"[twitter/generate] Warning: post is long ({word_count} words, max {max_words})")

        # Evaluate
        from engine.evaluator import evaluate, flatten_content
        eval_result = evaluate(
            flatten_content(result, "twitter"), "twitter", ticker
        )

        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            print(f"[twitter/generate] Attempt {attempt}: PASS (score {total_score}/15, {word_count} words)")
            return result

        print(f"[twitter/generate] Attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

    # All attempts failed — return last result anyway with warning
    if result:
        print(f"[twitter/generate] WARNING: returning content after {max_attempts} failed evaluations")
        return result
    raise RuntimeError(f"[twitter/generate] All {max_attempts} attempts failed for {ticker}")


def generate_to_file(
    report: ReportData,
    output_dir: Path | None = None,
) -> Path:
    """
    Generate content and save it to the archive directory.

    Returns:
        Path to the saved file.
    """
    ticker = report.metadata.ticker.upper()
    datestamp = datetime.now().strftime("%Y-%m-%d")

    if output_dir is None:
        output_dir = _ARCHIVE_DIR / ticker.lower()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    content = generate(report)
    word_count = len(content.split())

    filename = f"{datestamp}-post.txt"
    file_path = output_dir / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# Twitter Post for ${ticker}\n")
        f.write(f"# Generated: {datestamp}\n")
        f.write(f"# Words: {word_count}\n\n")
        f.write(content + "\n")

    print(f"[twitter/generate] Saved to {file_path}")
    return file_path


# ── CLI entry point ─────────────────────────────────────────────────────

def _cli():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Twitter/X long-form post from a 100Baggers report"
    )
    parser.add_argument("ticker", help="Stock ticker (e.g. AAPL)")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    ticker = args.ticker.lower()

    from engine.config import find_markdown_report
    from engine.markdown_parser import MarkdownReportParser

    en_path = find_english_markdown(ticker)
    zh_path = find_markdown_report(ticker)
    md_path = en_path or zh_path

    if not md_path:
        print(f"[twitter/generate] No report found for {ticker}")
        sys.exit(1)

    print(f"[twitter/generate] Parsing {md_path.name}...")
    report = MarkdownReportParser().parse(md_path)

    result = generate(report)
    word_count = len(result.split())
    print(f"\n{'=' * 60}")
    print(f"Post for ${ticker.upper()} ({word_count} words)")
    print(f"{'=' * 60}\n")
    print(result)

    path = generate_to_file(report, output_dir=args.output_dir)
    print(f"\nSaved to: {path}")


if __name__ == "__main__":
    _cli()
