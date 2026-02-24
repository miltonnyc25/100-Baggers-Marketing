"""
Markdown report parser — the primary parser for 100Baggers reports.

24 of 25 reports have .md source files; this parser is preferred over HTML.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from engine.report_schema import ReportData, ReportMetadata, ChapterContent


class MarkdownReportParser:
    """Parse a 100Baggers Markdown deep-research report into ReportData."""

    def parse(self, path: Path) -> ReportData:
        text = path.read_text(encoding="utf-8")
        metadata = self._extract_metadata(text, path)
        chapters = self._split_chapters(text)
        return ReportData(
            metadata=metadata,
            executive_summary=self._extract_executive_summary(text),
            core_contradiction=self._extract_core_contradiction(text),
            key_findings=self._extract_key_findings(text),
            critical_questions=self._extract_critical_questions(text),
            non_consensus_hypotheses=self._extract_non_consensus(text),
            financial_snapshot=self._extract_financial_snapshot(text),
            risk_factors=self._extract_risk_factors(text),
            bull_case=self._extract_section(text, ["bull case", "多头情景", "乐观情景"]),
            bear_case=self._extract_section(text, ["bear case", "空头情景", "悲观情景"]),
            valuation_summary=self._extract_section(text, ["估值", "valuation", "公允价值"]),
            chapters=chapters,
            raw_markdown=text,
        )

    # ── Metadata ──────────────────────────────────────────────────────

    def _extract_metadata(self, text: str, path: Path) -> ReportMetadata:
        ticker = self._guess_ticker(text, path)
        return ReportMetadata(
            ticker=ticker,
            company_name=self._first_table_value(text, "公司") or self._first_table_value(text, "Company") or "",
            exchange=self._guess_exchange(text),
            industry=self._first_table_value(text, "行业") or self._first_table_value(text, "Industry") or "",
            report_date=self._first_table_value(text, "数据截止") or self._first_table_value(text, "Data Date") or "",
            stock_price=self._first_table_value(text, "股价") or self._first_table_value(text, "Price") or "",
            market_cap=self._first_table_value(text, "市值") or self._first_table_value(text, "Market Cap") or "",
            ttm_revenue=self._first_table_value(text, "TTM收入") or self._first_table_value(text, "TTM Revenue") or "",
            report_type=self._first_table_value(text, "报告类型") or self._first_table_value(text, "Report Type") or "",
            framework_version=self._first_table_value(text, "框架版本") or "",
            language="en" if "/en/" in str(path) else "zh",
        )

    def _guess_ticker(self, text: str, path: Path) -> str:
        # Try filename first: SMCI_Complete_xxx.md
        stem = path.stem.upper()
        m = re.match(r"^([A-Z]{1,5})_", stem)
        if m:
            return m.group(1)
        # Try parent directory name
        return path.parent.name.upper()

    def _guess_exchange(self, text: str) -> str:
        for ex in ["NASDAQ", "NYSE", "TSE"]:
            if ex in text[:2000]:
                return ex
        return "NASDAQ"

    # ── Table value extraction ────────────────────────────────────────

    def _first_table_value(self, text: str, key: str) -> Optional[str]:
        """Extract first value from a markdown table row matching *key*."""
        pattern = rf"\|\s*\**{re.escape(key)}[^|]*\**\s*\|\s*(.+?)\s*\|"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().strip("*").strip()
            # Remove DM references like [DM-FIN-001]
            val = re.sub(r"\s*\[DM-[A-Z]+-\d+\]", "", val)
            return val
        return None

    # ── Chapter splitting ─────────────────────────────────────────────

    def _split_chapters(self, text: str) -> list[ChapterContent]:
        chapters = []
        # Split on ## heading (H2) that looks like a chapter
        pattern = r"^## (.+)$"
        parts = re.split(pattern, text, flags=re.MULTILINE)
        # parts = [preamble, title1, content1, title2, content2, ...]
        for i in range(1, len(parts) - 1, 2):
            title = parts[i].strip()
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            ch_id = f"ch{(i // 2) + 1}"
            tables = re.findall(r"(\|.+\|(?:\n\|.+\|)+)", content)
            chapters.append(ChapterContent(
                chapter_id=ch_id,
                title=title,
                content_markdown=content,
                tables=tables,
            ))
        return chapters

    # ── Section extraction helpers ────────────────────────────────────

    def _extract_executive_summary(self, text: str) -> str:
        return self._extract_section(text, [
            "核心结论速览", "报告总览", "executive summary",
            "核心矛盾", "core contradiction",
        ])

    def _extract_core_contradiction(self, text: str) -> str:
        # Look for the blockquote that usually holds the core contradiction
        m = re.search(r"^>\s*\*\*(.+?)\*\*\s*---\s*(.+?)$", text, re.MULTILINE)
        if m:
            return f"{m.group(1)} — {m.group(2)}"
        return self._extract_section(text, ["核心矛盾", "core contradiction"])

    def _extract_key_findings(self, text: str) -> list[str]:
        findings = []
        # Pattern: numbered list items under "核心发现" or "key findings"
        section = self._extract_section(text, ["核心发现", "key findings", "本章核心发现"])
        if section:
            for m in re.finditer(r"^\d+\.\s*\*\*(.+?)\*\*[:：]\s*(.+)$", section, re.MULTILINE):
                findings.append(f"{m.group(1)}: {m.group(2)}")
        if not findings:
            # Fallback: find all bold-colon patterns in first 5000 chars
            for m in re.finditer(r"\*\*(.+?)\*\*[:：]\s*(.+?)(?:\n|$)", text[:5000]):
                findings.append(f"{m.group(1)}: {m.group(2)}")
        return findings[:10]

    def _extract_critical_questions(self, text: str) -> list[dict]:
        cqs = []
        # Match CQ table rows: | CQ1 | question | type | weight | assessment |
        pattern = r"\|\s*CQ(\d+)\s*\|\s*(.+?)\s*\|\s*(\w+).*?\|\s*([\d.]+)\s*\|\s*(.+?)\s*\|"
        for m in re.finditer(pattern, text):
            cqs.append({
                "id": f"CQ{m.group(1)}",
                "question": m.group(2).strip(),
                "weight": m.group(4).strip(),
                "assessment": re.sub(r"\[.*?\]", "", m.group(5)).strip(),
            })
        return cqs

    def _extract_non_consensus(self, text: str) -> list[dict]:
        items = []
        pattern = r"\|\s*CI-(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|"
        for m in re.finditer(pattern, text):
            items.append({
                "id": f"CI-{m.group(1)}",
                "name": m.group(2).strip(),
                "consensus": m.group(3).strip(),
                "our_view": re.sub(r"\[.*?\]", "", m.group(4)).strip(),
            })
        return items

    def _extract_financial_snapshot(self, text: str) -> dict:
        snapshot: dict = {}
        kv_patterns = {
            "pe_ttm": r"PE\s*(?:TTM)?\s*[:=]?\s*([\d.]+)x?",
            "ps_ttm": r"PS\s*(?:TTM)?\s*[:=]?\s*([\d.]+)x?",
            "roe": r"ROE\s*[:=]?\s*([\d.]+)%",
            "roic": r"ROIC\s*[:=]?\s*([\d.]+)%",
            "gross_margin": r"(?:毛利率|Gross\s*Margin|GM)\s*[:=]?\s*([\d.]+)%",
            "net_margin": r"(?:净利率|Net\s*(?:Profit\s*)?Margin|NPM)\s*[:=]?\s*([\d.]+)%",
            "ttm_revenue": r"TTM[收营][入额]\s*[:=]?\s*\$?([\d.]+[BMK]?)",
            "fcf": r"(?:FCF|自由现金流)\s*[:=]?\s*\$?([-\d.]+[BMK]?)",
            "debt_equity": r"(?:Debt[/-]Equity|负债率|D/E)\s*[:=]?\s*([\d.]+)",
        }
        for key, pat in kv_patterns.items():
            m = re.search(pat, text[:8000], re.IGNORECASE)
            if m:
                snapshot[key] = m.group(1)
        return snapshot

    def _extract_risk_factors(self, text: str) -> list[str]:
        section = self._extract_section(text, [
            "风险", "risk", "最大风险", "risk factors",
        ])
        risks = []
        if section:
            for m in re.finditer(r"[-•]\s*\*?\*?(.+?)(?:\n|$)", section):
                risks.append(m.group(1).strip().strip("*"))
        return risks[:10]

    def _extract_section(self, text: str, keywords: list[str]) -> str:
        """Extract the text under a heading containing any of *keywords*."""
        for kw in keywords:
            # Match ## or ### heading containing the keyword
            pat = rf"^(#{2,3})\s+.*{re.escape(kw)}.*$"
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                level = len(m.group(1))
                start = m.end()
                # Find next heading of same or higher level
                next_heading = re.search(
                    rf"^#{{{1},{level}}}\s+", text[start:], re.MULTILINE
                )
                end = start + next_heading.start() if next_heading else start + 3000
                return text[start:end].strip()
        return ""
