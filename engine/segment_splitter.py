"""
Split a parsed ReportData into 3-5 thematic segments.

Each segment groups related chapters by keyword matching against canonical
themes.  Platform-specific segment counts are configurable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from engine.report_schema import ReportData, ChapterContent
from engine.segment_schema import SegmentData


# ── Theme definitions ────────────────────────────────────────────────

@dataclass
class ThemeDef:
    key: str
    title_zh: str
    title_en: str
    keywords: list[str]
    # Which ReportData fields to include as supplementary content
    include_fields: list[str] = field(default_factory=list)


THEMES = [
    ThemeDef(
        key="executive_overview",
        title_zh="核心概览",
        title_en="Executive Overview",
        keywords=[
            "executive summary", "核心结论", "core contradiction",
            "核心矛盾", "投资摘要", "investment thesis", "概述", "overview",
            "总结", "summary",
        ],
        include_fields=["executive_summary", "core_contradiction", "key_findings"],
    ),
    ThemeDef(
        key="financial_deep_dive",
        title_zh="财务深度分析",
        title_en="Financial Deep Dive",
        keywords=[
            "财务", "financial", "revenue", "收入", "利润", "margin",
            "dcf", "valuation", "估值", "盈利", "earnings", "现金流",
            "cash flow", "资产负债", "balance sheet", "营收",
        ],
        include_fields=["financial_snapshot"],
    ),
    ThemeDef(
        key="competitive_position",
        title_zh="竞争格局",
        title_en="Competitive Position",
        keywords=[
            "竞争", "competitive", "moat", "护城河", "market share",
            "市场份额", "行业", "industry", "对手", "competitor",
            "壁垒", "barrier", "差异化", "differentiation",
        ],
    ),
    ThemeDef(
        key="growth_technology",
        title_zh="增长与技术",
        title_en="Growth & Technology",
        keywords=[
            "业务", "business", "technology", "技术", "ai", "产品",
            "product", "增长", "growth", "创新", "innovation",
            "pipeline", "研发", "r&d", "expansion", "扩张",
        ],
    ),
    ThemeDef(
        key="risk_verdict",
        title_zh="风险与结论",
        title_en="Risk & Verdict",
        keywords=[
            "风险", "risk", "scenario", "bear case", "bull case",
            "看空", "看多", "情景", "downside", "upside", "挑战",
            "challenge", "不确定", "uncertainty",
        ],
        include_fields=["risk_factors", "bull_case", "bear_case"],
    ),
]

# Platform-specific segment configurations
PLATFORM_THEMES: dict[str, list[str]] = {
    "xueqiu": [
        "executive_overview",
        "financial_deep_dive",
        "competitive_position",
        "growth_technology",
        "risk_verdict",
    ],
    "xiaohongshu": [
        "executive_overview",
        "financial_deep_dive",
        "competitive_growth",   # merged: competitive + growth
        "risk_verdict",
    ],
    "twitter": [
        "executive_overview",
        "financial_data",       # financial only
        "risk_verdict",
    ],
    "youtube": [
        "executive_overview",
        "financial_deep_dive",
        "competitive_position",
        "growth_technology",
        "risk_verdict",
    ],
}

# Merged theme mappings: maps merged key -> list of canonical theme keys
MERGED_THEMES: dict[str, list[str]] = {
    "competitive_growth": ["competitive_position", "growth_technology"],
    "financial_data": ["financial_deep_dive"],
}


def _theme_by_key(key: str) -> Optional[ThemeDef]:
    for t in THEMES:
        if t.key == key:
            return t
    return None


def _match_chapter_to_theme(chapter: ChapterContent) -> Optional[str]:
    """Return the best-matching theme key for a chapter, or None.

    Scoring: title keywords are strongly weighted (5 pts each).
    Content-peek keywords only count if the title already has at least one
    hit, preventing noisy body text from dominating classification.
    """
    title_lower = chapter.title.lower()
    content_peek = chapter.content_markdown[:300].lower()

    best_theme = None
    best_score = 0

    for theme in THEMES:
        title_hits = sum(1 for kw in theme.keywords if kw in title_lower)
        # Only look at content if title already has a weak signal
        content_hits = 0
        if title_hits > 0:
            content_hits = sum(1 for kw in theme.keywords if kw in content_peek)
        score = title_hits * 5 + content_hits
        if score > best_score:
            best_score = score
            best_theme = theme.key

    # Require at least one title hit for a match
    return best_theme if best_score >= 5 else None


def _supplement_content(report: ReportData, field_name: str) -> str:
    """Extract supplementary content from ReportData fields."""
    val = getattr(report, field_name, None)
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        if val and isinstance(val[0], str):
            return "\n".join(f"- {item}" for item in val)
        if val and isinstance(val[0], dict):
            return "\n".join(str(item) for item in val)
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)
    return str(val)


class SegmentSplitter:
    """Split a ReportData into themed segments for a given platform."""

    def __init__(self, platform: str = "xueqiu"):
        self.platform = platform
        self.theme_keys = PLATFORM_THEMES.get(platform, PLATFORM_THEMES["xueqiu"])

    def split(self, report: ReportData) -> list[SegmentData]:
        """Split report chapters into themed segments."""
        # Step 1: Classify each chapter
        chapter_assignments: dict[str, list[ChapterContent]] = {
            key: [] for key in self._canonical_keys()
        }
        unassigned: list[ChapterContent] = []

        for ch in report.chapters:
            matched = _match_chapter_to_theme(ch)
            if matched and matched in chapter_assignments:
                chapter_assignments[matched].append(ch)
            else:
                unassigned.append(ch)

        # Step 2: Assign orphan chapters to nearest preceding segment
        if unassigned:
            canonical_order = self._canonical_keys()
            for ch in unassigned:
                # Find the chapter's position in the original list
                ch_idx = next(
                    (i for i, c in enumerate(report.chapters) if c.chapter_id == ch.chapter_id),
                    len(report.chapters),
                )
                # Find the nearest preceding assigned chapter's theme
                best_theme = canonical_order[-1]  # default: last theme
                for preceding_idx in range(ch_idx - 1, -1, -1):
                    preceding_ch = report.chapters[preceding_idx]
                    for theme_key, chapters in chapter_assignments.items():
                        if preceding_ch in chapters:
                            best_theme = theme_key
                            break
                    else:
                        continue
                    break
                chapter_assignments[best_theme].append(ch)

        # Step 3: Build segments (platform-aware theme merging)
        segments: list[SegmentData] = []
        for idx, theme_key in enumerate(self.theme_keys, 1):
            canonical_keys = MERGED_THEMES.get(theme_key, [theme_key])
            chapters: list[ChapterContent] = []
            for ck in canonical_keys:
                chapters.extend(chapter_assignments.get(ck, []))

            # Build content from chapters + supplementary fields
            content_parts: list[str] = []
            all_tables: list[str] = []
            chapter_ids: list[str] = []

            # Add supplementary ReportData fields
            for ck in canonical_keys:
                theme_def = _theme_by_key(ck)
                if theme_def:
                    for field_name in theme_def.include_fields:
                        supplement = _supplement_content(report, field_name)
                        if supplement:
                            content_parts.append(supplement)

            # Add chapter content
            for ch in chapters:
                content_parts.append(f"## {ch.title}\n\n{ch.content_markdown}")
                all_tables.extend(ch.tables)
                chapter_ids.append(ch.chapter_id)

            content_md = "\n\n".join(content_parts)

            # Determine title
            theme_def = _theme_by_key(canonical_keys[0])
            if theme_def:
                lang = report.metadata.language if report.metadata.language else "zh"
                title = theme_def.title_zh if lang == "zh" else theme_def.title_en
            else:
                title = theme_key.replace("_", " ").title()

            word_count = len(re.findall(r"\S+", content_md))

            segments.append(SegmentData(
                segment_id=f"seg{idx}",
                theme=theme_key,
                title=f"{report.metadata.ticker.upper()} - {title}",
                source_chapter_ids=chapter_ids,
                content_markdown=content_md,
                tables=all_tables,
                word_count=word_count,
            ))

        # Ensure no empty segments — merge into neighbor if content is empty
        return [s for s in segments if s.content_markdown.strip()]

    def _canonical_keys(self) -> list[str]:
        """Expand platform theme keys to canonical theme keys."""
        keys: list[str] = []
        for tk in self.theme_keys:
            if tk in MERGED_THEMES:
                keys.extend(MERGED_THEMES[tk])
            else:
                keys.append(tk)
        return keys
