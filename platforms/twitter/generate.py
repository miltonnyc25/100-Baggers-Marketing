#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter/X post generator for 100Baggers deep research reports.

Primary path: reads finished Xueqiu HTML posts → produces two English outputs:
  - Long-form (1500-2500 words): faithful translation of Xueqiu Chinese post
  - Short-form (200-300 words): distilled from the English long post

Fallback: if no Xueqiu output exists, uses the legacy raw-report path.

Usage:
    from platforms.twitter.generate import generate, generate_both, generate_to_file
    from engine.report_schema import ReportData

    result = generate_both("pltr")           # TwitterGenerationResult
    content = generate(report)               # str (long post, backward compat)
    path = generate_to_file(report)          # Path (saves both .html files)

CLI:
    python platforms/twitter/generate.py pltr --save --copy
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

# ── Resolve project root so engine imports work ─────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.report_schema import ReportData
from engine.config import (
    GEMINI_MODEL,
    REPORT_URL_TEMPLATE,
    find_english_markdown,
    get_company_name,
)
from engine.html_utils import save_html, copy_to_clipboard, strip_html_to_text

# ── Paths ───────────────────────────────────────────────────────────────
_PLATFORM_DIR = Path(__file__).resolve().parent
_LONG_PROMPT_PATH = _PLATFORM_DIR / "long_prompt.md"
_SHORT_PROMPT_PATH = _PLATFORM_DIR / "short_prompt.md"
_LEGACY_PROMPT_PATH = _PLATFORM_DIR / "prompt.md"
_CONFIG_PATH = _PLATFORM_DIR / "config.json"
_ARCHIVE_DIR = _PLATFORM_DIR / "archive"
_XUEQIU_ARCHIVE_DIR = _PLATFORM_DIR.parent / "xueqiu" / "archive"


# ── Result dataclass ───────────────────────────────────────────────────

@dataclass
class TwitterGenerationResult:
    long_post: str = ""
    short_post: str = ""
    source_path: Optional[Path] = None
    source_type: str = ""  # "xueqiu" or "legacy"


# ── Config / prompt loaders ────────────────────────────────────────────

def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_prompt(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── Xueqiu source discovery ───────────────────────────────────────────

def _find_xueqiu_source(ticker: str) -> Optional[Path]:
    """Find the newest .html file in xueqiu/archive/{ticker}/.

    Returns the path or None if no Xueqiu output exists.
    """
    ticker_dir = _XUEQIU_ARCHIVE_DIR / ticker.lower()
    if not ticker_dir.is_dir():
        return None

    html_files = sorted(
        ticker_dir.glob("*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # Pick the first non-strategy file
    for f in html_files:
        if "strategy" not in f.name.lower():
            return f
    return None


# ── Prompt builders ────────────────────────────────────────────────────

def _build_long_prompt(xueqiu_text: str, ticker: str, company: str) -> str:
    template = _load_prompt(_LONG_PROMPT_PATH)
    # Replace non-content placeholders first, then inject source text last
    # to avoid accidental replacement of {ticker} etc. inside source content
    filled = template.replace("{ticker}", ticker.upper()) \
                     .replace("{ticker_lower}", ticker.lower()) \
                     .replace("{company_name}", company)
    return filled.replace("{xueqiu_content}", xueqiu_text)


def _build_short_prompt(long_post_text: str, ticker: str, company: str) -> str:
    template = _load_prompt(_SHORT_PROMPT_PATH)
    filled = template.replace("{ticker}", ticker.upper()) \
                     .replace("{ticker_lower}", ticker.lower()) \
                     .replace("{company_name}", company)
    return filled.replace("{long_post_content}", long_post_text)


# ── Gemini caller ──────────────────────────────────────────────────────

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

    from engine.content_filter import clean_generated_content
    text = clean_generated_content(text)

    return text


# ── Compliance check ───────────────────────────────────────────────────

def _compliance_check(text: str) -> list[str]:
    config = _load_config()
    forbidden = config.get("compliance", {}).get("forbidden_words", [])
    violations = []
    text_lower = text.lower()
    for word in forbidden:
        if word.lower() in text_lower:
            violations.append(f"Forbidden word found: '{word}'")
    return violations


# ── Post-processing ────────────────────────────────────────────────────

def _postprocess(raw_output: str, ticker: str) -> str:
    """Clean up and ensure CTA link is present."""
    post = raw_output.strip().strip('"\'')
    cta_url = REPORT_URL_TEMPLATE.format(ticker=ticker.lower())
    if cta_url.lower() not in post.lower() and "100baggers.club" not in post.lower():
        post += f"\n\nData: {cta_url}"
    return post


# ── AI-language detection ──────────────────────────────────────────────

# Tier 1: words that instantly signal AI-generated content
_AI_WORDS_TIER1 = [
    "delve", "delves", "delving",
    "landscape", "tapestry", "realm", "arena",
    "robust",
    "leveraging", "leverage",
    "pivotal", "crucial", "vital",
    "game-changer", "game-changing", "game changer",
    "meticulous", "showcasing", "underscores",
    "multifaceted", "nuanced", "comprehensive",
    "navigate", "navigating",
    "foster", "fostering",
    "streamline", "embark",
    "furthermore,", "moreover,", "additionally,",
    "it's worth noting",
    "in the ever-evolving",
    "this is a testament",
    "let's unpack", "let's break down",
    "dive deep", "deep dive",
]


def _check_ai_words(text: str) -> list[str]:
    """Check for AI-signal words that destroy credibility on X."""
    found = []
    text_lower = text.lower()
    for word in _AI_WORDS_TIER1:
        if word in text_lower:
            found.append(word)
    return found


# ── Core eval loop for a single post variant ──────────────────────────

def _generate_post(
    source_text: str,
    ticker: str,
    company: str,
    variant: str,  # "long" or "short"
    max_attempts: int = 5,
) -> Optional[str]:
    """Generate a single post variant (long or short) with eval loop.

    Args:
        source_text: For "long" variant, this is the Xueqiu Chinese text.
                     For "short" variant, this is the English long post.

    Enforcements before evaluator:
    1. Word count within range
    2. No AI-signal words (credibility killer on X)

    Then runs Gemini evaluator for quality scoring.
    """
    config = _load_config()

    if variant == "long":
        build_fn = _build_long_prompt
        min_words = config.get("long_min_words", 1500)
        max_words = config.get("long_max_words", 2500)
    else:
        build_fn = _build_short_prompt
        min_words = config.get("short_min_words", 200)
        max_words = config.get("short_max_words", 300)

    rewrite_instructions = ""
    result = None

    for attempt in range(1, max_attempts + 1):
        prompt = build_fn(source_text, ticker, company)
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
            print(f"[twitter/generate] {variant} attempt {attempt} failed: {exc}")
            break

        result = _postprocess(raw_output, ticker)
        word_count = len(result.split())

        # Enforcement 1: word count
        if word_count < min_words:
            gap = min_words - word_count
            print(f"[twitter/generate] {variant} attempt {attempt}: TOO SHORT "
                  f"({word_count} words, min {min_words}, need +{gap})")
            if variant == "long":
                rewrite_instructions = (
                    f"CRITICAL LENGTH FAILURE: Post is {word_count} words but minimum is {min_words}. "
                    f"You need {gap} MORE words. You are translating the FULL source — do not omit or "
                    f"summarize any sections. Go back to the source and translate every argument, "
                    f"every data point, every section that you skipped."
                )
            else:
                rewrite_instructions = (
                    f"Post is {word_count} words but minimum is {min_words}. "
                    f"You need {gap} MORE words. Add more supporting data or expand the evidence."
                )
            continue

        if word_count > max_words:
            print(f"[twitter/generate] {variant} attempt {attempt}: TOO LONG "
                  f"({word_count} words, max {max_words})")
            rewrite_instructions = (
                f"Post is {word_count} words. Maximum is {max_words} words. "
                f"Cut ruthlessly — remove filler, tighten sentences, "
                f"keep only the strongest data points."
            )
            continue

        # Enforcement 2: no AI-signal words
        ai_words = _check_ai_words(result)
        if ai_words:
            print(f"[twitter/generate] {variant} attempt {attempt}: AI words detected: {ai_words}")
            rewrite_instructions = (
                f"CRITICAL: Your post contains words that signal AI-generated content "
                f"and will destroy credibility on X: {', '.join(ai_words)}. "
                f"Replace every single one. Use natural, conversational language. "
                f"Write like a human analyst, not a language model."
            )
            continue

        # Evaluate with Gemini
        from engine.evaluator import evaluate, flatten_content
        eval_result = evaluate(
            flatten_content(result, "twitter"), "twitter", ticker.upper()
        )

        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            print(f"[twitter/generate] {variant} attempt {attempt}: PASS "
                  f"(score {total_score}/15, {word_count} words)")
            return result

        print(f"[twitter/generate] {variant} attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

    # All attempts exhausted — return last result with warning
    if result:
        print(f"[twitter/generate] WARNING: returning {variant} content after "
              f"{max_attempts} failed evaluations")
        return result
    return None


# ── Primary entry: generate both variants ─────────────────────────────

def generate_both(
    ticker: str,
    xueqiu_path: Optional[Path] = None,
) -> TwitterGenerationResult:
    """Generate long-form and short-form X posts from Xueqiu source.

    Args:
        ticker: Stock ticker (e.g. "pltr")
        xueqiu_path: Explicit path to Xueqiu HTML file. If None, auto-discovers.

    Returns:
        TwitterGenerationResult with long_post and short_post.
    """
    ticker_upper = ticker.upper()
    company = get_company_name(ticker_upper)

    # Find Xueqiu source
    if xueqiu_path is None:
        xueqiu_path = _find_xueqiu_source(ticker)

    if xueqiu_path is None or not xueqiu_path.exists():
        print(f"[twitter/generate] No Xueqiu source found for {ticker_upper}")
        return TwitterGenerationResult(source_type="none")

    print(f"[twitter/generate] Using Xueqiu source: {xueqiu_path.name}")

    # Convert HTML to plain text
    xueqiu_text = strip_html_to_text(xueqiu_path)
    if len(xueqiu_text) < 200:
        print(f"[twitter/generate] Xueqiu text too short ({len(xueqiu_text)} chars)")
        return TwitterGenerationResult(source_type="none")

    print(f"[twitter/generate] Xueqiu text: {len(xueqiu_text)} chars")

    result = TwitterGenerationResult(
        source_path=xueqiu_path,
        source_type="xueqiu",
    )

    # Generate long post (translate Xueqiu Chinese → English)
    print(f"[twitter/generate] Generating long-form post for {ticker_upper}...")
    result.long_post = _generate_post(xueqiu_text, ticker, company, "long") or ""

    # Generate short post (distill from English long post)
    if result.long_post:
        print(f"[twitter/generate] Generating short-form post for {ticker_upper}...")
        result.short_post = _generate_post(result.long_post, ticker, company, "short") or ""
    else:
        print(f"[twitter/generate] Skipping short post — no long post available")

    return result


# ── Backward-compatible public API ────────────────────────────────────

def generate(report: ReportData, max_attempts: int = 3) -> str:
    """Generate a long-form Twitter/X post from a ReportData object.

    Primary path: find Xueqiu HTML source → long-form adaptation.
    Fallback: legacy raw-report generation.

    Returns the post content as a string.
    """
    ticker = report.metadata.ticker.upper()

    # Try Xueqiu-sourced generation first
    xueqiu_path = _find_xueqiu_source(ticker)
    if xueqiu_path:
        company = get_company_name(ticker)
        xueqiu_text = strip_html_to_text(xueqiu_path)
        if len(xueqiu_text) >= 200:
            print(f"[twitter/generate] Xueqiu source found: {xueqiu_path.name}")
            result = _generate_post(
                xueqiu_text, ticker, company, "long", max_attempts
            )
            if result:
                return result
            print("[twitter/generate] Xueqiu-sourced generation failed, trying legacy")

    # Legacy fallback
    return _generate_from_report_legacy(report, max_attempts)


def _generate_from_report_legacy(
    report: ReportData, max_attempts: int = 3
) -> str:
    """Legacy generation path: raw report → prompt.md → Gemini.

    Used for tickers with no Xueqiu output.
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
        prompt = _build_legacy_prompt(report)
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
            print(f"[twitter/generate] Legacy attempt {attempt} failed: {exc}")
            break

        result = _postprocess(raw_output, ticker)

        # Check word count
        word_count = len(result.split())
        min_words = config.get("post_min_words", 300)
        max_words = config.get("post_max_words", 500)
        if word_count < min_words:
            print(f"[twitter/generate] Warning: legacy post short ({word_count} words)")
        elif word_count > max_words:
            print(f"[twitter/generate] Warning: legacy post long ({word_count} words)")

        # Evaluate
        from engine.evaluator import evaluate, flatten_content
        eval_result = evaluate(
            flatten_content(result, "twitter"), "twitter", ticker
        )

        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            print(f"[twitter/generate] Legacy attempt {attempt}: PASS "
                  f"(score {total_score}/15, {word_count} words)")
            return result

        print(f"[twitter/generate] Legacy attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

    if result:
        print(f"[twitter/generate] WARNING: returning legacy content after "
              f"{max_attempts} failed evaluations")
        return result
    raise RuntimeError(f"[twitter/generate] All {max_attempts} legacy attempts failed for {ticker}")


# ── Legacy prompt builder (uses prompt.md) ─────────────────────────────

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


def _build_legacy_prompt(report: ReportData) -> str:
    template = _load_prompt(_LEGACY_PROMPT_PATH)
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


# ── File output ────────────────────────────────────────────────────────

def generate_to_file(
    report: ReportData,
    output_dir: Path | None = None,
) -> Path:
    """Generate content and save to the archive directory.

    If Xueqiu source exists: saves both long and short as .html files.
    Otherwise: saves legacy single post as .txt.

    Returns:
        Path to the primary output file (long post).
    """
    ticker = report.metadata.ticker.upper()
    datestamp = datetime.now().strftime("%Y-%m-%d")

    if output_dir is None:
        output_dir = _ARCHIVE_DIR / ticker.lower()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Try Xueqiu-sourced dual output
    xueqiu_path = _find_xueqiu_source(ticker)
    if xueqiu_path:
        result = generate_both(ticker, xueqiu_path)
        if result.long_post or result.short_post:
            first_path = None

            if result.long_post:
                long_html = output_dir / f"{ticker}-twitter-long-{datestamp}.html"
                save_html(result.long_post, long_html)
                print(f"[twitter/generate] Saved {long_html.name}")

                long_txt = output_dir / f"{ticker}-twitter-long-{datestamp}.txt"
                word_count = len(result.long_post.split())
                long_txt.write_text(
                    f"# X/Twitter Long Post for ${ticker}\n"
                    f"# Generated: {datestamp}\n"
                    f"# Words: {word_count}\n"
                    f"# Source: {xueqiu_path.name}\n\n"
                    + result.long_post + "\n",
                    encoding="utf-8",
                )
                print(f"[twitter/generate] Saved {long_txt.name} ({word_count} words)")
                first_path = long_html

            if result.short_post:
                short_html = output_dir / f"{ticker}-twitter-short-{datestamp}.html"
                save_html(result.short_post, short_html)
                print(f"[twitter/generate] Saved {short_html.name}")

                short_txt = output_dir / f"{ticker}-twitter-short-{datestamp}.txt"
                word_count = len(result.short_post.split())
                short_txt.write_text(
                    f"# X/Twitter Short Post for ${ticker}\n"
                    f"# Generated: {datestamp}\n"
                    f"# Words: {word_count}\n"
                    f"# Source: {xueqiu_path.name}\n\n"
                    + result.short_post + "\n",
                    encoding="utf-8",
                )
                print(f"[twitter/generate] Saved {short_txt.name} ({word_count} words)")
                if first_path is None:
                    first_path = short_html

            return first_path

    # Legacy fallback: single post
    content = _generate_from_report_legacy(report)
    word_count = len(content.split())

    filename = f"{datestamp}-post.txt"
    file_path = output_dir / filename
    file_path.write_text(
        f"# Twitter Post for ${ticker}\n"
        f"# Generated: {datestamp}\n"
        f"# Words: {word_count}\n\n"
        + content + "\n",
        encoding="utf-8",
    )
    print(f"[twitter/generate] Saved legacy {file_path.name}")
    return file_path


# ── CLI entry point ─────────────────────────────────────────────────────

def _cli():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate X/Twitter posts from Xueqiu analysis (or raw report fallback)"
    )
    parser.add_argument("ticker", help="Stock ticker (e.g. PLTR)")
    parser.add_argument("--save", action="store_true", help="Save output to archive/")
    parser.add_argument("--copy", action="store_true", help="Copy long post to clipboard (macOS)")
    parser.add_argument("--short-only", action="store_true", help="Generate short post only")
    parser.add_argument("--long-only", action="store_true", help="Generate long post only")
    parser.add_argument("--legacy", action="store_true", help="Force legacy report-based generation")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    ticker = args.ticker.lower()
    ticker_upper = ticker.upper()

    # Legacy mode: use raw report
    if args.legacy:
        from engine.config import find_markdown_report
        from engine.markdown_parser import MarkdownReportParser

        en_path = find_english_markdown(ticker)
        zh_path = find_markdown_report(ticker)
        md_path = en_path or zh_path
        if not md_path:
            print(f"[twitter/generate] No report found for {ticker}")
            sys.exit(1)

        print(f"[twitter/generate] Legacy mode: parsing {md_path.name}...")
        report = MarkdownReportParser().parse(md_path)
        content = _generate_from_report_legacy(report)
        word_count = len(content.split())
        print(f"\n{'=' * 60}")
        print(f"Legacy Post for ${ticker_upper} ({word_count} words)")
        print(f"{'=' * 60}\n")
        print(content)
        return

    # Primary mode: Xueqiu-sourced
    xueqiu_path = _find_xueqiu_source(ticker)
    if not xueqiu_path:
        print(f"[twitter/generate] No Xueqiu source for {ticker_upper}. "
              f"Use --legacy for raw report path.")
        sys.exit(1)

    company = get_company_name(ticker_upper)
    xueqiu_text = strip_html_to_text(xueqiu_path)
    print(f"[twitter/generate] Source: {xueqiu_path.name} ({len(xueqiu_text)} chars)")

    outputs = {}

    if not args.short_only:
        print(f"\n[twitter/generate] Generating long-form (translate from Xueqiu)...")
        long_post = _generate_post(xueqiu_text, ticker, company, "long")
        if long_post:
            outputs["long"] = long_post

    if not args.long_only:
        # Short post is distilled from the English long post
        long_source = outputs.get("long")
        if not long_source:
            # If --short-only, we need to generate long first as intermediate
            print(f"\n[twitter/generate] Generating long-form first (needed for short)...")
            long_source = _generate_post(xueqiu_text, ticker, company, "long")
        if long_source:
            print(f"\n[twitter/generate] Generating short-form (distill from long)...")
            short_post = _generate_post(long_source, ticker, company, "short")
            if short_post:
                outputs["short"] = short_post
        else:
            print(f"[twitter/generate] Cannot generate short — no long post available")

    # Display results
    for variant, content in outputs.items():
        word_count = len(content.split())
        print(f"\n{'=' * 60}")
        print(f"{variant.upper()} Post for ${ticker_upper} ({word_count} words)")
        print(f"{'=' * 60}\n")
        print(content)

    if not outputs:
        print("[twitter/generate] No posts generated.")
        sys.exit(1)

    # Save
    if args.save:
        datestamp = datetime.now().strftime("%Y-%m-%d")
        out_dir = args.output_dir or (_ARCHIVE_DIR / ticker)
        out_dir.mkdir(parents=True, exist_ok=True)

        for variant, content in outputs.items():
            word_count = len(content.split())

            html_path = out_dir / f"{ticker_upper}-twitter-{variant}-{datestamp}.html"
            save_html(content, html_path)
            print(f"\nSaved: {html_path}")

            txt_path = out_dir / f"{ticker_upper}-twitter-{variant}-{datestamp}.txt"
            txt_path.write_text(
                f"# X/Twitter {variant.title()} Post for ${ticker_upper}\n"
                f"# Generated: {datestamp}\n"
                f"# Words: {word_count}\n"
                f"# Source: {xueqiu_path.name}\n\n"
                + content + "\n",
                encoding="utf-8",
            )
            print(f"Saved: {txt_path}")

        # Copy long post to clipboard
        if args.copy and "long" in outputs:
            long_html = out_dir / f"{ticker_upper}-twitter-long-{datestamp}.html"
            if long_html.exists() and copy_to_clipboard(long_html):
                print("\nCopied long post to clipboard")


if __name__ == "__main__":
    _cli()
