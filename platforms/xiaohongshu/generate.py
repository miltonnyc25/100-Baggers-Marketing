#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaohongshu (小红书) slide deck + caption generator.

Takes a ReportData object from the engine and produces:
  - title  (<=20 chars, catchy, with emoji)
  - slides (5 strings, one core insight each)
  - caption (500-1000 chars with numbered takeaways + hashtags + disclaimer)

Uses Gemini AI with the prompt template in prompt.md.
Falls back to template-based generation when AI is unavailable.

Output is saved as {ticker}_xiaohongshu.md in archive/{ticker}/.
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Resolve project root so engine imports work ──────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.report_schema import ReportData
from engine.config import GEMINI_MODEL

# ── Platform config ──────────────────────────────────────────────────

_PLATFORM_DIR = Path(__file__).resolve().parent
_PROMPT_PATH = _PLATFORM_DIR / "prompt.md"
_CONFIG_PATH = _PLATFORM_DIR / "config.json"
_ARCHIVE_DIR = _PLATFORM_DIR / "archive"

with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    PLATFORM_CONFIG: dict = json.load(_f)

TITLE_MAX = PLATFORM_CONFIG["title_max_chars"]
CAPTION_MIN = PLATFORM_CONFIG["caption_min_chars"]
CAPTION_MAX = PLATFORM_CONFIG["caption_max_chars"]
SLIDES_COUNT = PLATFORM_CONFIG["slides_count"]
SENSITIVE_TOPICS: list[str] = PLATFORM_CONFIG["compliance"]["sensitive_topics"]
ATTRIBUTION_PREFIX: str = PLATFORM_CONFIG["compliance"]["attribution_prefix"]
REQUIRED_DISCLAIMER: str = PLATFORM_CONFIG["compliance"]["required_disclaimer"]
DEFAULT_HASHTAGS: list[str] = PLATFORM_CONFIG["hashtags"]


# =====================================================================
# Compliance helpers
# =====================================================================

def _filter_sensitive(text: str) -> str:
    """Remove sentences that contain sensitive keywords."""
    if not text:
        return text
    lines = text.split("\n")
    clean = []
    for line in lines:
        if any(kw in line for kw in SENSITIVE_TOPICS):
            continue
        clean.append(line)
    return "\n".join(clean)


def _ensure_attribution(text: str) -> str:
    """Prefix valuation opinions with the required attribution."""
    opinion_patterns = [
        (r"(?<!据分析)(被低估)", rf"{ATTRIBUTION_PREFIX}，\1"),
        (r"(?<!据分析)(被高估)", rf"{ATTRIBUTION_PREFIX}，\1"),
        (r"(?<!据分析)(低估\s*\d+%)", rf"{ATTRIBUTION_PREFIX}，\1"),
        (r"(?<!据分析)(高估\s*\d+%)", rf"{ATTRIBUTION_PREFIX}，\1"),
        (r"(?<!据分析)(目标价\s*[\$￥]\d+)", rf"{ATTRIBUTION_PREFIX}，\1"),
    ]
    for pat, repl in opinion_patterns:
        text = re.sub(pat, repl, text)
    return text


def _apply_compliance(content: dict) -> dict:
    """Run sensitive-topic filter and attribution on all text fields."""
    content["title"] = _filter_sensitive(content["title"])[:TITLE_MAX]
    content["slides"] = [
        _ensure_attribution(_filter_sensitive(s))
        for s in content["slides"]
    ]
    content["caption"] = _ensure_attribution(
        _filter_sensitive(content["caption"])
    )
    # Guarantee disclaimer is present
    if REQUIRED_DISCLAIMER not in content["caption"]:
        content["caption"] = content["caption"].rstrip() + "\n\n" + REQUIRED_DISCLAIMER
    return content


# =====================================================================
# Prompt rendering
# =====================================================================

def _render_prompt(report: ReportData) -> str:
    """Render the prompt.md template with report data."""
    prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    key_findings_str = "\n".join(
        f"- {f}" for f in report.top_findings(5)
    ) if report.key_findings else "(not available)"

    snapshot_str = json.dumps(
        report.financial_snapshot, ensure_ascii=False, indent=2
    ) if report.financial_snapshot else "(not available)"

    prompt = prompt_template.replace("{ticker}", report.metadata.ticker.upper())
    prompt = prompt.replace("{ticker_lower}", report.metadata.ticker.lower())
    prompt = prompt.replace("{company_name}", report.metadata.company_name)
    prompt = prompt.replace("{executive_summary}", report.executive_summary[:2000] or "(not available)")
    prompt = prompt.replace("{key_findings}", key_findings_str)
    prompt = prompt.replace("{financial_snapshot}", snapshot_str)

    return prompt


# =====================================================================
# AI generation (Gemini)
# =====================================================================

def _repair_truncated_json(raw: str) -> Optional[dict]:
    """Attempt to repair truncated JSON from Gemini response."""
    # Strip code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```\s*$", "", raw)

    if not raw.startswith("{"):
        return None

    # Try progressively closing the JSON
    # Count open brackets/braces
    attempts = [
        raw + '"}]}',      # truncated inside a string in slides array
        raw + '"],"caption":""}',  # truncated in slides, missing caption
        raw + '"}',         # truncated inside caption
        raw + '"}],"caption":""}',  # truncated in slide string
        raw + '"]}',        # truncated after last slide
    ]
    for attempt in attempts:
        try:
            data = json.loads(attempt)
            if isinstance(data, dict) and "title" in data and "slides" in data:
                # Ensure caption exists
                data.setdefault("caption", "")
                return data
        except json.JSONDecodeError:
            continue
    return None


def _call_gemini(prompt: str) -> Optional[dict]:
    """Call Google Gemini and return parsed JSON content dict."""
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
            "You are a JSON-only API. Return a single JSON object with keys "
            '"title" (string), "slides" (array of exactly 5 strings), "caption" (string). '
            "No markdown fences, no explanation, no extra keys. Output ONLY valid JSON."
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

    raw = response.text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)

    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find a complete JSON object
        match = re.search(r"\{[\s\S]+\}", raw)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                # Try to repair truncated JSON by closing open structures
                repaired = _repair_truncated_json(raw)
                if repaired:
                    data = repaired
                else:
                    print(f"[xiaohongshu/generate] JSON parse failed, raw: {raw[:300]}")
                    return None
        else:
            # Response might be truncated with no closing brace
            repaired = _repair_truncated_json(raw)
            if repaired:
                data = repaired
            else:
                print(f"[xiaohongshu/generate] No JSON found in response: {raw[:300]}")
                return None

    if not isinstance(data, dict):
        return None

    # Validate and repair structure
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        return None

    slides = data.get("slides", [])
    if not isinstance(slides, list):
        return None
    # Accept 3-7 slides (lenient), then pad or trim to SLIDES_COUNT
    if len(slides) < 3:
        return None
    # Pad with filler if slightly short
    while len(slides) < SLIDES_COUNT:
        slides.append("完整报告请访问 https://www.100baggers.club")
    data["slides"] = slides[:SLIDES_COUNT]

    if not isinstance(data.get("caption"), str) or not data["caption"].strip():
        return None

    # Post-generation filter: strip Mermaid/code from text fields
    from engine.content_filter import strip_mermaid_and_code, strip_price_targets
    for key in ("title", "caption"):
        if key in data and isinstance(data[key], str):
            data[key] = strip_mermaid_and_code(data[key])
            data[key] = strip_price_targets(data[key])
    data["slides"] = [strip_price_targets(strip_mermaid_and_code(s)) for s in data["slides"]]

    return data


# =====================================================================
# Template-based fallback
# =====================================================================

def _generate_from_template(report: ReportData) -> dict:
    """Produce slide deck content using static templates (no AI)."""
    ticker = report.metadata.ticker.upper()
    company = report.metadata.company_name or ticker

    # ── Title ──
    title = f"{company}深度研报解读"
    if len(title) > TITLE_MAX:
        title = f"{ticker}深度研报解读"
    if len(title) > TITLE_MAX:
        title = f"{ticker}深度解读"

    # ── Slides ──
    findings = report.top_findings(5)

    slide_1 = f"你了解{company}吗？一份深度研报帮你看清全貌"
    if report.executive_summary:
        hook = report.executive_summary[:50].rstrip("。，、")
        slide_1 = f"{company}：{hook}..."

    core_slides: list[str] = []
    for i, finding in enumerate(findings[:3]):
        text = finding[:60].rstrip("。，、")
        core_slides.append(f"核心发现{i + 1}：{text}")
    # Pad if fewer than 3 findings
    while len(core_slides) < 3:
        if report.financial_snapshot:
            snap_items = list(report.financial_snapshot.items())
            if snap_items:
                k, v = snap_items[len(core_slides) % len(snap_items)]
                core_slides.append(f"财务指标：{k} = {v}")
            else:
                core_slides.append(f"{company}值得关注的核心逻辑")
        else:
            core_slides.append(f"{company}值得关注的核心逻辑")

    slide_5 = f"完整{ticker}深度报告请访问 https://www.100baggers.club/reports/{ticker.lower()}"

    slides = [slide_1] + core_slides[:3] + [slide_5]

    # ── Caption ──
    numbered = ""
    for i, finding in enumerate(findings[:5], 1):
        emoji_num = f"{i}\ufe0f\u20e3"
        line = finding[:80].rstrip("。，、")
        numbered += f"{emoji_num} {line}\n"

    hashtags_extra = [ticker, company.replace(" ", "")]
    all_tags = DEFAULT_HASHTAGS + hashtags_extra
    hashtag_str = " ".join(f"#{t}" for t in all_tags)

    caption = textwrap.dedent(f"""\
        {company}（${ticker}）深度研报要点速览

        {numbered}
        完整报告请访问 https://www.100baggers.club/reports/{ticker.lower()}

        {hashtag_str}

        {REQUIRED_DISCLAIMER}""")

    # Ensure minimum length
    if len(caption) < CAPTION_MIN and report.executive_summary:
        summary_excerpt = report.executive_summary[:300]
        caption = (
            f"{company}（${ticker}）深度研报要点速览\n\n"
            f"{summary_excerpt}\n\n"
            f"{numbered}\n"
            f"完整报告请访问 https://www.100baggers.club/reports/{ticker.lower()}\n\n"
            f"{hashtag_str}\n\n"
            f"{REQUIRED_DISCLAIMER}"
        )

    # Trim to max
    if len(caption) > CAPTION_MAX:
        # Keep disclaimer at the end
        body = caption[: caption.rfind("\n\n" + REQUIRED_DISCLAIMER)]
        body = body[: CAPTION_MAX - len(REQUIRED_DISCLAIMER) - 4]
        caption = body.rstrip() + "\n\n" + REQUIRED_DISCLAIMER

    return {
        "title": title[:TITLE_MAX],
        "slides": slides[:SLIDES_COUNT],
        "caption": caption,
    }


# =====================================================================
# Final price-target safety net (runs after compliance, before return)
# =====================================================================

def _final_price_filter(content: dict) -> dict:
    """Strip any price targets that survived earlier filters."""
    from engine.content_filter import strip_price_targets
    for key in ("title", "caption"):
        if key in content and isinstance(content[key], str):
            content[key] = strip_price_targets(content[key])
    content["slides"] = [strip_price_targets(s) for s in content["slides"]]
    return content


# =====================================================================
# Public API
# =====================================================================

def generate(report: ReportData, max_attempts: int = 3) -> dict:
    """
    Generate Xiaohongshu content from a ReportData object.

    Uses evaluate→rewrite loop: generates, evaluates with Gemini,
    regenerates with feedback if quality issues are found.

    Returns:
        dict with keys: "title" (str), "slides" (list[str]), "caption" (str)
    """
    ticker = report.metadata.ticker.upper()
    rewrite_instructions = ""

    api_available = True
    for attempt in range(1, max_attempts + 1):
        try:
            prompt = _render_prompt(report)
            if rewrite_instructions:
                prompt = (
                    f"REWRITE REQUIRED — your previous output was rejected.\n"
                    f"Issues found: {rewrite_instructions}\n"
                    f"Fix ALL issues listed above. Do NOT repeat the same mistakes.\n\n"
                    + prompt
                )
            ai_result = _call_gemini(prompt)
            if ai_result is None:
                if attempt == 1:
                    # Check if it's an API availability issue vs parse failure
                    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                    if not api_key:
                        api_available = False
                        break  # No API key — go to template
                print(f"[xiaohongshu/generate] Attempt {attempt}: AI returned invalid JSON, retrying...")
                continue  # Retry — don't give up on parse failures

            result = _apply_compliance(ai_result)

            # Evaluate
            from engine.evaluator import evaluate, flatten_content
            eval_result = evaluate(
                flatten_content(result, "xiaohongshu"), "xiaohongshu", ticker
            )

            passed = eval_result.get("pass", True)
            violations = eval_result.get("violations", [])
            total_score = eval_result.get("total_score", 0)

            if passed and not violations:
                print(f"[xiaohongshu/generate] Attempt {attempt}: PASS (score {total_score}/15)")
                return _final_price_filter(result)

            print(f"[xiaohongshu/generate] Attempt {attempt}: FAIL — {violations}")
            rewrite_instructions = eval_result.get("rewrite_instructions", "")
            if not rewrite_instructions:
                rewrite_instructions = "; ".join(violations)

        except Exception as exc:
            print(f"[xiaohongshu/generate] Attempt {attempt} failed ({exc})")
            if attempt >= max_attempts:
                break
            continue  # Retry on errors

    # All attempts exhausted — fall back to template
    print(f"[xiaohongshu/generate] Using template fallback")
    result = _generate_from_template(report)
    return _apply_compliance(result)


def generate_to_file(report: ReportData, output_dir: Optional[Path] = None) -> Path:
    """
    Generate content and write it to a Markdown file.

    The file is saved as {ticker}_xiaohongshu.md inside
    archive/{ticker}/ (or the provided output_dir).

    Returns:
        Path to the written file.
    """
    content = generate(report)
    ticker = report.metadata.ticker.lower()

    if output_dir is None:
        output_dir = _ARCHIVE_DIR / ticker
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f"{ticker}_xiaohongshu.md"

    slides_md = ""
    for i, slide in enumerate(content["slides"], 1):
        slides_md += f"### Slide {i}\n{slide}\n\n"

    md = textwrap.dedent(f"""\
        ---
        platform: xiaohongshu
        ticker: {ticker.upper()}
        company: {report.metadata.company_name}
        generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ---

        # {content["title"]}

        ## Slides

        {slides_md}
        ## Caption

        {content["caption"]}
    """)

    out_path.write_text(md, encoding="utf-8")
    print(f"[xiaohongshu/generate] Saved: {out_path}")
    return out_path


# =====================================================================
# CLI
# =====================================================================

if __name__ == "__main__":
    """Quick test: python generate.py <ticker>"""
    from engine.config import find_markdown_report
    from engine.markdown_parser import MarkdownReportParser

    if len(sys.argv) < 2:
        print("Usage: python generate.py <ticker>")
        print("Example: python generate.py tsla")
        sys.exit(1)

    ticker = sys.argv[1].lower()
    md_path = find_markdown_report(ticker)
    if not md_path:
        print(f"No markdown report found for {ticker}")
        sys.exit(1)

    parser = MarkdownReportParser()
    report = parser.parse(md_path)

    content = generate(report)
    print(f"\n{'=' * 60}")
    print(f"Title: {content['title']}")
    print(f"{'=' * 60}")
    for i, slide in enumerate(content["slides"], 1):
        print(f"\nSlide {i}: {slide}")
    print(f"\n{'=' * 60}")
    print(f"Caption ({len(content['caption'])} chars):")
    print(content["caption"])

    out = generate_to_file(report)
    print(f"\nFile: {out}")
