#!/usr/bin/env python3
"""
YouTube video script & description generator.

Takes a ReportData object (from the engine) and uses Gemini AI to produce
a complete YouTube content package: title, description, video script, tags,
and timestamps.

Usage (as module):
    from platforms.youtube.generate import generate, generate_to_file
    result = generate(report)
    path   = generate_to_file(report, output_dir)

Usage (CLI):
    python platforms/youtube/generate.py <ticker>
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Resolve project root so imports work from any cwd ─────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.report_schema import ReportData
from engine.config import (
    GEMINI_MODEL,
    VENV_PYTHON,
    REPORT_URL_TEMPLATE,
    PRODUCTION_URL,
)

# ── Constants ─────────────────────────────────────────────────────────

PLATFORM_DIR = Path(__file__).resolve().parent
PROMPT_PATH = PLATFORM_DIR / "prompt.md"
CONFIG_PATH = PLATFORM_DIR / "config.json"
ARCHIVE_DIR = PLATFORM_DIR / "archive"

# Load platform config
with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    CONFIG = json.load(_f)

TITLE_MAX_CHARS = CONFIG.get("title_max_chars", 70)
DESCRIPTION_MAX_WORDS = CONFIG.get("description_max_words", 400)
SCRIPT_MIN_MINUTES = CONFIG.get("script_min_minutes", 5)
SCRIPT_MAX_MINUTES = CONFIG.get("script_max_minutes", 15)
DISCLAIMER = CONFIG["compliance"]["required_disclaimer"]
ATTRIBUTION = CONFIG["compliance"]["attribution"]


# ── Helpers ───────────────────────────────────────────────────────────

def _log(level: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"info": "INFO", "ok": " OK ", "warn": "WARN", "err": " ERR"}
    print(f"[{ts}] [{prefix.get(level, 'INFO')}] {msg}")


def _format_key_findings(findings: list[str]) -> str:
    if not findings:
        return "(none provided)"
    return "\n".join(f"- {f}" for f in findings)


def _format_financial_snapshot(snapshot: dict) -> str:
    if not snapshot:
        return "(none provided)"
    lines = []
    for k, v in snapshot.items():
        label = k.replace("_", " ").upper()
        lines.append(f"- {label}: {v}")
    return "\n".join(lines)


def _format_risk_factors(risks: list[str]) -> str:
    if not risks:
        return "(none provided)"
    return "\n".join(f"- {r}" for r in risks)


def _build_prompt(report: ReportData) -> str:
    """Read prompt.md and fill in template variables from the report."""
    template = PROMPT_PATH.read_text(encoding="utf-8")

    ticker = report.metadata.ticker.upper()
    company_name = report.metadata.company_name or ticker

    replacements = {
        "{ticker}": ticker,
        "{ticker_lower}": ticker.lower(),
        "{company_name}": company_name,
        "{executive_summary}": report.executive_summary or "(none provided)",
        "{key_findings}": _format_key_findings(report.key_findings),
        "{financial_snapshot}": _format_financial_snapshot(report.financial_snapshot),
        "{risk_factors}": _format_risk_factors(report.risk_factors),
        "{bull_case}": report.bull_case or "(none provided)",
        "{bear_case}": report.bear_case or "(none provided)",
    }

    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)

    return prompt


def _call_gemini(prompt: str) -> dict:
    """Call Gemini API and parse the JSON response."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required. "
            "Set it before running: export GEMINI_API_KEY='your-key'"
        )

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    _log("info", f"Calling Gemini ({GEMINI_MODEL})...")
    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown code fences if present
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0]

    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log("err", f"Failed to parse Gemini response as JSON: {exc}")
        _log("err", f"Raw response (first 500 chars): {raw[:500]}")
        raise

    # Post-generation filter: strip Mermaid/code from text fields
    from engine.content_filter import strip_mermaid_and_code, strip_price_targets
    for key in ("title", "description", "script"):
        if key in result and isinstance(result[key], str):
            result[key] = strip_mermaid_and_code(result[key])
            result[key] = strip_price_targets(result[key])

    return result


def _strip_special_chars(text: str) -> str:
    """Remove special Unicode characters, emojis, and decorative symbols from text."""
    import unicodedata
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        # Keep ASCII, basic Latin, digits, punctuation, whitespace
        if ord(ch) < 128:
            cleaned.append(ch)
        # Keep CJK characters (for tags that might have them)
        elif '\u4e00' <= ch <= '\u9fff':
            cleaned.append(ch)
        # Keep basic Latin supplement (accented chars etc)
        elif '\u00c0' <= ch <= '\u024f':
            cleaned.append(ch)
        # Skip emojis, symbols, decorative chars
        elif cat.startswith(('So', 'Sk', 'Sm', 'Sc')):
            continue
        # Skip emoji modifiers and variation selectors
        elif cat.startswith('Mn') or cat.startswith('Cf'):
            continue
        else:
            cleaned.append(ch)
    return ''.join(cleaned)


def _validate(result: dict, report: ReportData) -> dict:
    """Validate and sanitise the Gemini output against platform constraints."""
    ticker = report.metadata.ticker.upper()

    # ── Title ─────────────────────────────────────────────────────────
    title = result.get("title", f"{ticker}: Deep Research Analysis")
    title = _strip_special_chars(title)
    if len(title) > TITLE_MAX_CHARS:
        truncated = title[: TITLE_MAX_CHARS - 3].rsplit(" ", 1)[0] + "..."
        _log("warn", f"Title truncated from {len(title)} to {len(truncated)} chars")
        title = truncated
    result["title"] = title

    # ── Description ───────────────────────────────────────────────────
    description = result.get("description", "")
    # Strip special chars and emojis
    description = _strip_special_chars(description)
    # Strip any markdown formatting that leaked through
    description = re.sub(r'\*\*([^*]+)\*\*', r'\1', description)  # bold
    description = re.sub(r'\*([^*]+)\*', r'\1', description)  # italic
    description = re.sub(r'^#+\s*', '', description, flags=re.MULTILINE)  # headers
    description = re.sub(r'^[-*]\s+', '', description, flags=re.MULTILINE)  # bullets
    # Ensure report link is present
    report_url = REPORT_URL_TEMPLATE.format(ticker=ticker.lower())
    if report_url not in description and "100baggers.club" not in description.lower():
        description = description.rstrip() + f"\nFull report: {report_url}"
    # Ensure disclaimer is present
    if DISCLAIMER not in description:
        description = description.rstrip() + f"\n{DISCLAIMER}\n{ATTRIBUTION}"
    # Check word count
    desc_words = len(description.split())
    if desc_words > DESCRIPTION_MAX_WORDS + 30:  # 30 word buffer for disclaimer
        _log("warn", f"Description is long: {desc_words} words (max {DESCRIPTION_MAX_WORDS})")
    result["description"] = description

    # ── Script ────────────────────────────────────────────────────────
    script = result.get("script", "")
    word_count = len(script.split())
    est_minutes = word_count / 130
    if est_minutes < SCRIPT_MIN_MINUTES:
        _log("warn", f"Script is short: ~{est_minutes:.1f} min ({word_count} words)")
    elif est_minutes > SCRIPT_MAX_MINUTES:
        _log("warn", f"Script is long: ~{est_minutes:.1f} min ({word_count} words)")
    else:
        _log("ok", f"Script length: ~{est_minutes:.1f} min ({word_count} words)")

    # ── Tags ──────────────────────────────────────────────────────────
    tags = result.get("tags", [])
    essential = [ticker, "stock analysis", "investing", "100Baggers"]
    for tag in essential:
        if tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag)
    result["tags"] = tags

    # ── Timestamps ────────────────────────────────────────────────────
    timestamps = result.get("timestamps", [])
    if not timestamps:
        ts_pattern = r"\[(\d{1,2}:\d{2}(?:-\d{1,2}:\d{2})?)\]\s*(.+)"
        for m in re.finditer(ts_pattern, script):
            time_range = m.group(1)
            label = m.group(2).strip().rstrip("*").strip()
            start_time = time_range.split("-")[0]
            timestamps.append(f"{start_time} {label}")
    result["timestamps"] = timestamps

    return result


# ── Public API ────────────────────────────────────────────────────────


def generate(report: ReportData, max_attempts: int = 3) -> dict:
    """
    Generate YouTube content from a ReportData object.

    Uses evaluate→rewrite loop: generates, evaluates with Gemini,
    regenerates with feedback if quality issues are found.

    Returns:
        dict with keys: title, description, script, tags, timestamps
    """
    ticker = report.metadata.ticker.upper()
    _log("info", f"Generating YouTube content for {ticker}...")

    rewrite_instructions = ""
    result = None

    for attempt in range(1, max_attempts + 1):
        prompt = _build_prompt(report)
        if rewrite_instructions:
            prompt = (
                f"⚠️ REWRITE REQUIRED — your previous output was rejected.\n"
                f"Issues found: {rewrite_instructions}\n"
                f"Fix ALL issues. Do NOT repeat the same mistakes.\n\n"
                + prompt
            )

        try:
            result = _call_gemini(prompt)
            result = _validate(result, report)
        except Exception as exc:
            _log("err", f"Attempt {attempt} failed: {exc}")
            break

        # Evaluate
        from engine.evaluator import evaluate, flatten_content
        eval_result = evaluate(
            flatten_content(result, "youtube"), "youtube", ticker
        )

        passed = eval_result.get("pass", True)
        violations = eval_result.get("violations", [])
        total_score = eval_result.get("total_score", 0)

        if passed and not violations:
            _log("ok", f"Attempt {attempt}: PASS (score {total_score}/15)")
            _log("ok", f"YouTube content generated for {ticker}")
            _log("info", f"  Title: {result['title']}")
            _log("info", f"  Tags: {', '.join(result['tags'][:5])}...")
            _log("info", f"  Timestamps: {len(result['timestamps'])} entries")
            return result

        _log("warn", f"Attempt {attempt}: FAIL — {violations}")
        rewrite_instructions = eval_result.get("rewrite_instructions", "")
        if not rewrite_instructions:
            rewrite_instructions = "; ".join(violations)

    _log("warn", f"Returning content after {max_attempts} attempts")
    return result


def generate_to_file(report: ReportData, output_dir: Optional[Path] = None) -> Path:
    """
    Generate YouTube content and save to files.

    Outputs:
        {output_dir}/{ticker}_youtube_script.md
        {output_dir}/{ticker}_youtube_description.md

    The output_dir defaults to platforms/youtube/archive/{ticker}/

    Returns:
        Path to the output directory containing both files.
    """
    ticker = report.metadata.ticker.upper()
    result = generate(report)

    # Determine output directory
    if output_dir is None:
        output_dir = ARCHIVE_DIR / ticker.lower()
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Save script ───────────────────────────────────────────────────
    script_path = output_dir / f"{ticker}_youtube_script.md"
    script_content = f"""# {result['title']}

## Video Script

{result['script']}

---

## Timestamps

{chr(10).join(result['timestamps'])}

---

## Tags

{', '.join(result['tags'])}

---

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    script_path.write_text(script_content, encoding="utf-8")
    _log("ok", f"Script saved: {script_path}")

    # ── Save description ──────────────────────────────────────────────
    desc_path = output_dir / f"{ticker}_youtube_description.md"
    desc_content = f"""{result['description']}

---

Timestamps:
{chr(10).join(result['timestamps'])}

---

Tags: {', '.join(f'#{t.replace(" ", "")}' for t in result['tags'])}
"""
    desc_path.write_text(desc_content, encoding="utf-8")
    _log("ok", f"Description saved: {desc_path}")

    # ── Save raw JSON for programmatic use ────────────────────────────
    json_path = output_dir / f"{ticker}_youtube_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    _log("ok", f"JSON data saved: {json_path}")

    return output_dir


# ── CLI entrypoint ────────────────────────────────────────────────────

def main():
    """CLI: python generate.py <ticker> [--output-dir PATH]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate YouTube video script & description from a 100Baggers report."
    )
    parser.add_argument("ticker", help="Stock ticker (e.g. TSLA, AAPL)")
    parser.add_argument(
        "--output-dir", "-o",
        help="Output directory (default: archive/{ticker}/)",
        default=None,
    )
    parser.add_argument(
        "--english", "-e",
        action="store_true",
        help="Use English report source if available",
    )

    args = parser.parse_args()
    ticker = args.ticker.upper()

    # Parse the report using the engine
    from engine.config import find_english_markdown, find_markdown_report
    from engine.markdown_parser import MarkdownReportParser

    if args.english:
        md_path = find_english_markdown(ticker.lower())
    else:
        md_path = find_markdown_report(ticker.lower())

    if md_path is None:
        _log("err", f"No report found for ticker: {ticker}")
        _log("err", "Available tickers: check ~/Downloads/InvestView_v0/public/reports/")
        sys.exit(1)

    _log("info", f"Parsing report: {md_path}")
    report_parser = MarkdownReportParser()
    report = report_parser.parse(md_path)

    output_dir = Path(args.output_dir) if args.output_dir else None
    result_dir = generate_to_file(report, output_dir)

    _log("ok", f"All files saved to: {result_dir}")


if __name__ == "__main__":
    main()
