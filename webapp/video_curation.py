"""
Video curation pipeline: angle recommendation + document curation.

Thin wrapper around engine.content_strategist, preserving the existing
function signatures that webapp/app.py expects.

Step 1: Gemini reads full report → recommends 2-3 video angles with 5-dimension scoring.
Step 2: User picks an angle → Gemini curates a 30,000+ char document from the report.
"""

from __future__ import annotations

import logging

from engine.report_schema import ReportData, ReportMetadata
from engine.content_strategist import (
    recommend_angles as _recommend,
    curate_content as _curate,
    ContentAngle,
)

log = logging.getLogger(__name__)

VIDEO_ANGLE_INSTRUCTIONS = """\
## 视频平台特殊要求

- 推荐2-3个角度（不是1个）
- 每个角度必须能支撑5-10分钟的视频讨论
- 讨论锚点(discussion_anchors)必须包含具体数据，AI主持人会直接引用
- 包含audience_aha_moment字段：观众看完后最可能的顿悟时刻
"""

VIDEO_CURATION_CONTEXT = (
    "策展文档将被直接作为 NotebookLM 的源材料输入。"
    "NotebookLM 会基于这份文档，由两位 AI 主持人展开一场 5-10 分钟的"
    "中文深度投资讨论视频。AI 主持人无法讨论文档中没有的内容。"
)


def _build_report_from_text(ticker: str, company_name: str, report_content: str) -> ReportData:
    """Build a minimal ReportData from raw text (webapp passes strings, not ReportData)."""
    return ReportData(
        metadata=ReportMetadata(
            ticker=ticker,
            company_name=company_name,
        ),
        raw_markdown=report_content,
    )


def recommend_angles(ticker: str, company_name: str, report_content: str) -> list[dict]:
    """Call Gemini to recommend 2-3 video angles from the full report.

    Backward-compatible wrapper: webapp/app.py calls this with raw strings.
    Returns a list of angle dicts with scores.
    """
    report = _build_report_from_text(ticker, company_name, report_content)
    result = _recommend(
        report,
        platform_instructions=VIDEO_ANGLE_INSTRUCTIONS,
        max_angles=3,
    )
    if not result or not result.angles:
        return []

    return [a.to_dict() for a in result.angles]


def curate_document(
    ticker: str, company_name: str, report_content: str, selected_angle: dict,
) -> str:
    """Call Gemini to curate a 30k+ char document for the selected angle.

    Backward-compatible wrapper: webapp/app.py calls this with raw strings.
    Returns the curated markdown document.
    """
    report = _build_report_from_text(ticker, company_name, report_content)
    angle = ContentAngle.from_dict(selected_angle)
    curated = _curate(
        report, angle,
        platform_instructions=VIDEO_CURATION_CONTEXT,
    )
    if not curated:
        raise RuntimeError("Content curation returned empty result")
    return curated
