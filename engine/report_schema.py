"""
Standardised data classes for parsed report content.

ReportData is the interface between the engine (parser) and the platform
content generators.  Every platform's generate.py receives a ReportData
and produces platform-native output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReportMetadata:
    ticker: str
    company_name: str
    exchange: str = "NASDAQ"
    industry: str = ""
    report_date: str = ""
    stock_price: str = ""
    market_cap: str = ""
    ttm_revenue: str = ""
    report_type: str = ""
    framework_version: str = ""
    language: str = "zh"  # "zh" or "en"


@dataclass
class ChapterContent:
    chapter_id: str  # e.g. "ch1", "ch2"
    title: str
    content_markdown: str
    tables: list[str] = field(default_factory=list)  # raw markdown tables
    section: str = "free"  # "free", "registered", "paid"


@dataclass
class ReportData:
    metadata: ReportMetadata
    executive_summary: str = ""
    core_contradiction: str = ""
    key_findings: list[str] = field(default_factory=list)
    critical_questions: list[dict] = field(default_factory=list)  # [{id, question, weight, assessment}]
    non_consensus_hypotheses: list[dict] = field(default_factory=list)  # [{id, name, consensus, our_view}]
    financial_snapshot: dict = field(default_factory=dict)  # {pe, ps, roe, roic, gm, npm, fcf, ...}
    risk_factors: list[str] = field(default_factory=list)
    bull_case: str = ""
    bear_case: str = ""
    valuation_summary: str = ""
    chapters: list[ChapterContent] = field(default_factory=list)
    raw_markdown: str = ""  # full original text for fallback

    # ── Convenience helpers ───────────────────────────────────────────

    def top_findings(self, n: int = 5) -> list[str]:
        """Return the first *n* key findings."""
        return self.key_findings[:n]

    def chapter_by_keyword(self, keyword: str) -> ChapterContent | None:
        """Find the first chapter whose title contains *keyword*."""
        kw = keyword.lower()
        for ch in self.chapters:
            if kw in ch.title.lower():
                return ch
        return None

    def snippet(self, max_chars: int = 3000) -> str:
        """Return a truncated version of the raw markdown."""
        if len(self.raw_markdown) <= max_chars:
            return self.raw_markdown
        return self.raw_markdown[:max_chars] + "\n\n…[truncated]"
