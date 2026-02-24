"""
Generate platform content for individual segments.

Constructs a synthetic mini-ReportData from each SegmentData and delegates
to the existing platform generators — zero modifications to platform code.
"""

from __future__ import annotations

import importlib
import logging
import re
from copy import deepcopy

from engine.report_schema import ReportData, ReportMetadata, ChapterContent
from engine.segment_schema import SegmentData

log = logging.getLogger(__name__)


def _build_mini_report(segment: SegmentData, report: ReportData, platform: str = "") -> ReportData:
    """Construct a focused ReportData from a segment's content."""
    meta = deepcopy(report.metadata)

    # Build a single synthetic chapter from the segment content
    chapter = ChapterContent(
        chapter_id=segment.segment_id,
        title=segment.title,
        content_markdown=segment.content_markdown,
        tables=segment.tables,
    )

    # Selectively include report-level fields based on theme
    theme = segment.theme
    include_financial = "financial" in theme or "data" in theme
    include_risk = "risk" in theme or "verdict" in theme
    include_executive = "executive" in theme or "overview" in theme
    include_growth = "growth" in theme or "competitive" in theme

    # For executive overview, use the full executive summary & key findings
    exec_summary = ""
    key_findings = []
    if include_executive:
        exec_summary = report.executive_summary
        key_findings = report.key_findings
    else:
        # Use first 1500 chars of segment content as summary
        exec_summary = segment.content_markdown[:1500]
        # Extract bullet-point-like findings from segment content
        key_findings = _extract_segment_findings(segment)

    # For xueqiu, pre-filter to data-dense paragraphs
    raw_md = segment.content_markdown
    if platform == "xueqiu":
        raw_md = _select_compelling_content(segment.content_markdown, max_chars=8000)

    return ReportData(
        metadata=meta,
        executive_summary=exec_summary,
        core_contradiction=report.core_contradiction if include_executive else "",
        key_findings=key_findings,
        critical_questions=report.critical_questions if include_executive else [],
        non_consensus_hypotheses=report.non_consensus_hypotheses if include_executive else [],
        financial_snapshot=report.financial_snapshot if include_financial or include_executive else {},
        risk_factors=report.risk_factors if include_risk else [],
        bull_case=report.bull_case if include_risk else "",
        bear_case=report.bear_case if include_risk else "",
        valuation_summary=report.valuation_summary if include_financial else "",
        chapters=[chapter],
        raw_markdown=raw_md,
    )


def _extract_segment_findings(segment: SegmentData) -> list[str]:
    """Extract bullet-point findings from segment markdown."""
    findings = []
    for line in segment.content_markdown.split("\n"):
        line = line.strip()
        # Match numbered list items or bold-prefixed bullets
        if line and (
            (line[0].isdigit() and ". " in line[:5])
            or line.startswith("- **")
            or line.startswith("* **")
        ):
            findings.append(line)
        if len(findings) >= 5:
            break
    return findings


def _select_compelling_content(content_markdown: str, max_chars: int = 8000) -> str:
    """Pick data-dense paragraphs from segment content for xueqiu generation."""
    paragraphs = content_markdown.split("\n\n")
    scored: list[tuple[float, str]] = []

    for p in paragraphs:
        text = p.strip()
        if len(text) < 30:
            continue
        if text.startswith("#"):
            continue
        num_count = len(re.findall(r"[\d,.]+[%$BMKx倍亿万]|\$[\d,.]+[BMK]?", text))
        has_comparison = any(w in text for w in
                            ["vs", "而", "但", "相比", "增长", "下降", "增至", "降至",
                             "同比", "环比", "较", "超过", "达到"])
        score = num_count * 2 + (1 if has_comparison else 0) + min(len(text) / 200, 3)
        scored.append((score, text))

    scored.sort(key=lambda x: x[0], reverse=True)

    result_parts: list[str] = []
    total = 0
    for _, p in scored:
        if total + len(p) > max_chars:
            break
        result_parts.append(p)
        total += len(p)

    return "\n\n".join(result_parts)


def generate_segment_content(
    segment: SegmentData,
    report: ReportData,
    platform: str,
) -> dict | str:
    """
    Generate platform content for a single segment.

    Returns whatever the platform's generate() returns:
      - xueqiu: str
      - xiaohongshu: dict {title, slides, caption}
      - twitter: str | list[str]
      - youtube: dict {title, description, script, tags, timestamps}
    """
    mini_report = _build_mini_report(segment, report, platform=platform)

    gen_mod = importlib.import_module(f"platforms.{platform}.generate")
    log.info("Generating %s content for segment %s", platform, segment.segment_id)

    try:
        result = gen_mod.generate(mini_report)
    except Exception:
        log.exception("Generation failed for %s / %s", platform, segment.segment_id)
        raise

    return result


def generate_all_segments(
    segments: list[SegmentData],
    report: ReportData,
    platform: str,
) -> list[SegmentData]:
    """
    Generate content for all segments and store results in platform_content.

    Returns the same segment list with platform_content populated.
    """
    for seg in segments:
        try:
            content = generate_segment_content(seg, report, platform)
            seg.platform_content[platform] = content
        except Exception:
            log.warning(
                "Skipping segment %s due to generation error", seg.segment_id
            )
            seg.platform_content[platform] = {"error": "Generation failed"}
    return segments
