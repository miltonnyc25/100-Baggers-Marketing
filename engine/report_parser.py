"""
HTML report parser for 100Baggers investment reports.

Extracts structured content from index.html across all three gated
content regions (free / registered / paid).

Key design notes:
- Chapters are <h1>, sections are <h2>, sub-sections are <h3>
- Three content regions must ALL be read (free-content, registered-content, paid-content)
- Tables are converted to compact Markdown for readability (not flattened via get_text)
- Mermaid diagrams are stripped before extraction
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from engine.report_schema import ReportData, ReportMetadata, ChapterContent

try:
    from bs4 import BeautifulSoup, Tag, NavigableString
except ImportError:
    BeautifulSoup = None  # type: ignore


class HTMLReportParser:
    """Parse an index.html report into ReportData."""

    def __init__(self) -> None:
        if BeautifulSoup is None:
            raise ImportError(
                "beautifulsoup4 is required for HTML parsing: "
                "pip install beautifulsoup4"
            )

    def parse(self, path: Path) -> ReportData:
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # Remove noise before any extraction
        self._strip_noise(soup)

        metadata = self._extract_metadata(soup, path)
        body_text = self._extract_body_text(soup)
        chapters = self._split_chapters(soup)

        return ReportData(
            metadata=metadata,
            executive_summary=self._extract_executive_summary(soup),
            core_contradiction=self._extract_core_contradiction(soup),
            key_findings=self._extract_key_findings(soup),
            financial_snapshot=self._extract_financial_snapshot(soup, body_text),
            risk_factors=self._extract_risks(soup),
            bull_case=self._section_prose(soup, [
                "多头情景", "bull case", "乐观情景", "乐观",
            ]),
            bear_case=self._section_prose(soup, [
                "空头情景", "bear case", "悲观情景", "悲观",
            ]),
            valuation_summary=self._extract_valuation_summary(soup),
            chapters=chapters,
            raw_markdown=body_text,
        )

    # ── Noise removal ─────────────────────────────────────────────────

    def _strip_noise(self, soup: BeautifulSoup) -> None:
        """Remove scripts, styles, mermaid diagrams, and nav/footer."""
        for tag in soup.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()
        for tag in soup.find_all(class_=re.compile(r"mermaid", re.I)):
            tag.decompose()
        for tag in soup.find_all("div", class_=re.compile(r"mermaid", re.I)):
            tag.decompose()
        # Also remove invite overlay
        overlay = soup.find(id="invite-guide-overlay")
        if overlay:
            overlay.decompose()

    # ── Content regions ───────────────────────────────────────────────

    def _get_all_content_regions(self, soup: BeautifulSoup) -> list[Tag]:
        """Return all three gated content divs (free + registered + paid)."""
        regions = []
        for region_id in ["free-content", "registered-content", "paid-content"]:
            region = soup.find(id=region_id)
            if region:
                regions.append(region)
        if not regions:
            body = soup.find("body")
            if body:
                regions = [body]
        return regions

    # ── Metadata ──────────────────────────────────────────────────────

    def _extract_metadata(self, soup: BeautifulSoup, path: Path) -> ReportMetadata:
        ld = soup.find("script", type="application/ld+json")
        if ld:
            try:
                data = json.loads(ld.string)
                return ReportMetadata(
                    ticker=data.get("ticker", path.parent.name.upper()),
                    company_name=data.get("name", ""),
                    industry=data.get("industry", ""),
                    report_date=data.get("datePublished", ""),
                    language="en" if "/en/" in str(path) else "zh",
                )
            except (json.JSONDecodeError, AttributeError):
                pass

        ticker = path.parent.name.upper()
        if ticker == "EN":
            ticker = path.parent.parent.name.upper()

        # Prefer first <h1> (has real company name) over <title> (sometimes generic)
        company_name = ""
        first_h1 = soup.find("h1")
        if first_h1:
            raw = first_h1.get_text(strip=True)
            # Trim trailing report title boilerplate
            for suffix in ["深度投资研究报告", "In-Depth Investment Research Report",
                           "In-depth Investment Research Report", "Deep Investment Research Report",
                           "深度研究报告", "投资研究报告"]:
                raw = raw.replace(suffix, "").strip().rstrip(" -—")
            company_name = raw.strip()
        if not company_name or "UNKNOWN" in company_name:
            title_tag = soup.find("title")
            company_name = title_tag.get_text(strip=True) if title_tag else ticker

        return ReportMetadata(
            ticker=ticker,
            company_name=company_name,
            language="en" if "/en/" in str(path) else "zh",
        )

    # ── Body text (all regions combined) ──────────────────────────────

    def _extract_body_text(self, soup: BeautifulSoup) -> str:
        """Extract full body text from ALL content regions.

        Prose (<p>, <li>, <blockquote>) is kept as-is.
        Tables are converted to compact Markdown format.
        """
        parts = []
        for region in self._get_all_content_regions(soup):
            parts.append(self._region_to_text(region))
        return "\n\n".join(parts)

    def _region_to_text(self, region: Tag) -> str:
        """Convert a content region to readable text, handling tables specially."""
        output = []
        for child in region.children:
            if not isinstance(child, Tag):
                continue
            if child.name == "table":
                output.append(self._table_to_markdown(child))
            elif child.name in ("h1", "h2", "h3"):
                level = int(child.name[1])
                prefix = "#" * level
                output.append(f"{prefix} {child.get_text(strip=True)}")
            else:
                text = child.get_text(separator="\n", strip=True)
                if text:
                    output.append(text)
        return "\n\n".join(output)

    def _table_to_markdown(self, table: Tag) -> str:
        """Convert an HTML table to compact Markdown table format."""
        rows = table.find_all("tr")
        if not rows:
            return ""
        md_rows = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            md_rows.append("| " + " | ".join(
                c.get_text(strip=True).replace("|", "/") for c in cells
            ) + " |")
        if len(md_rows) >= 2:
            # Insert separator after header row
            ncols = md_rows[0].count("|") - 1
            separator = "| " + " | ".join(["---"] * max(ncols, 1)) + " |"
            md_rows.insert(1, separator)
        return "\n".join(md_rows)

    # ── Chapters (split on <h1>) ──────────────────────────────────────

    def _split_chapters(self, soup: BeautifulSoup) -> list[ChapterContent]:
        """Split report into chapters using <h1> headings."""
        chapters = []
        all_h1s = []
        for region in self._get_all_content_regions(soup):
            all_h1s.extend(region.find_all("h1"))

        for i, h1 in enumerate(all_h1s):
            title = h1.get_text(strip=True)
            # Skip the report title (first h1 is usually the main title)
            if i == 0 and ("深度" in title or "研究报告" in title or "Research" in title):
                continue

            # Collect content between this h1 and the next h1
            parts = []
            tables = []
            for sib in h1.find_next_siblings():
                if isinstance(sib, Tag):
                    if sib.name == "h1":
                        break
                    if sib.name == "table":
                        tables.append(self._table_to_markdown(sib))
                        continue
                    text = sib.get_text(separator="\n", strip=True)
                    if text:
                        parts.append(text)

            content = "\n\n".join(parts)
            chapters.append(ChapterContent(
                chapter_id=f"ch{len(chapters) + 1}",
                title=title,
                content_markdown=content,
                tables=tables[:10],
            ))
        return chapters

    # ── Executive summary ─────────────────────────────────────────────

    def _extract_executive_summary(self, soup: BeautifulSoup) -> str:
        """Extract executive summary from Chapter 1.

        Looks for specific h2 markers: 一句话结论, 三个核心发现,
        Executive Summary — these live in the first chapter.
        """
        # Strategy: find "一句话结论" or "三个核心发现" in free-content
        free = soup.find(id="free-content")
        search_root = free if free else soup

        parts = []

        # Try "一句话结论" first
        conclusion = self._find_heading_in(search_root, ["一句话结论", "one-line", "核心结论"])
        if conclusion:
            parts.append(self._prose_after_heading(conclusion, max_chars=1000))

        # Then "三个核心发现" or "key findings"
        findings = self._find_heading_in(search_root, ["三个核心发现", "核心发现", "key findings"])
        if findings:
            parts.append(self._prose_after_heading(findings, max_chars=2000))

        if parts:
            return "\n\n".join(p for p in parts if p)

        # Fallback: first h1 chapter content
        first_h1 = search_root.find("h1")
        if first_h1:
            return self._prose_after_heading(first_h1, max_chars=3000)

        return ""

    def _extract_core_contradiction(self, soup: BeautifulSoup) -> str:
        """Extract the core contradiction (核心矛盾)."""
        # Often in a blockquote near the top
        free = soup.find(id="free-content")
        search_root = free if free else soup

        heading = self._find_heading_in(search_root, ["核心矛盾", "core contradiction"])
        if heading:
            return self._prose_after_heading(heading, max_chars=1000)

        # Try blockquote in first chapter
        bq = search_root.find("blockquote")
        if bq:
            return bq.get_text(strip=True)[:1000]

        return ""

    # ── Key findings ──────────────────────────────────────────────────

    def _extract_key_findings(self, soup: BeautifulSoup) -> list[str]:
        """Extract key findings as a list of strings."""
        free = soup.find(id="free-content")
        search_root = free if free else soup

        heading = self._find_heading_in(search_root, [
            "三个核心发现", "核心发现", "key findings", "本章核心发现",
        ])
        if heading:
            # Collect list items or bold-text patterns after this heading
            findings = []
            for sib in heading.find_next_siblings():
                if isinstance(sib, Tag):
                    if sib.name in ("h1", "h2") and sib != heading:
                        break
                    # Ordered/unordered list items
                    for li in sib.find_all("li"):
                        text = li.get_text(strip=True)
                        if len(text) > 15:
                            findings.append(text)
                    # Bold-colon patterns in paragraphs
                    if sib.name == "p":
                        strong = sib.find("strong")
                        if strong:
                            full = sib.get_text(strip=True)
                            if len(full) > 20:
                                findings.append(full)
            if findings:
                return findings[:10]

        # Fallback: numbered patterns in full body text
        body_text = self._extract_body_text(soup)
        findings = []
        for m in re.finditer(r"\d+\.\s*\*?\*?(.+?)(?:\n|$)", body_text[:8000]):
            line = m.group(1).strip().strip("*")
            if len(line) > 20:
                findings.append(line)
        return findings[:10]

    # ── Financial snapshot ────────────────────────────────────────────

    def _extract_financial_snapshot(self, soup: BeautifulSoup, body_text: str) -> dict:
        """Extract financial metrics from tables and text."""
        snapshot: dict = {}

        # Strategy 1: search ALL text (not just first 8000 chars)
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
            m = re.search(pat, body_text, re.IGNORECASE)
            if m:
                snapshot[key] = m.group(1)

        # Strategy 2: look for summary tables with financial data
        for region in self._get_all_content_regions(soup):
            for table in region.find_all("table"):
                for row in table.find_all("tr"):
                    cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
                    if len(cells) >= 2:
                        label = cells[0].lower()
                        value = cells[1]
                        if "pe" in label and "ttm" in label and "pe_ttm" not in snapshot:
                            m = re.search(r"([\d.]+)", value)
                            if m:
                                snapshot["pe_ttm"] = m.group(1)
                        elif "毛利率" in label or "gross margin" in label.lower():
                            m = re.search(r"([\d.]+)", value)
                            if m and "gross_margin" not in snapshot:
                                snapshot["gross_margin"] = m.group(1)
                        elif "roe" in label and "roe" not in snapshot:
                            m = re.search(r"([\d.]+)", value)
                            if m:
                                snapshot["roe"] = m.group(1)

        return snapshot

    # ── Risk factors ──────────────────────────────────────────────────

    def _extract_risks(self, soup: BeautifulSoup) -> list[str]:
        """Extract risk factors from dedicated risk sections."""
        risks = []

        # Look for risk-related headings across all regions
        for region in self._get_all_content_regions(soup):
            for h in region.find_all(["h1", "h2", "h3"]):
                title = h.get_text(strip=True).lower()
                if any(kw in title for kw in ["风险", "risk", "kill switch", "黑天鹅"]):
                    for sib in h.find_next_siblings():
                        if isinstance(sib, Tag):
                            if sib.name in ("h1", "h2") and sib != h:
                                break
                            for li in sib.find_all("li"):
                                text = li.get_text(strip=True)
                                if len(text) > 10:
                                    risks.append(text)
                            # Also catch bold items in paragraphs
                            if sib.name == "p":
                                strong = sib.find("strong")
                                if strong and len(sib.get_text(strip=True)) > 15:
                                    risks.append(sib.get_text(strip=True))
                    if risks:
                        break  # Found a risk section, stop searching
            if risks:
                break

        return risks[:10]

    # ── Valuation summary ─────────────────────────────────────────────

    def _extract_valuation_summary(self, soup: BeautifulSoup) -> str:
        """Extract valuation analysis (from paid-content chapters, not TOC)."""
        # Look in paid-content first (that's where real valuation lives)
        paid = soup.find(id="paid-content")
        if paid:
            heading = self._find_heading_in(paid, ["估值", "valuation", "公允价值"])
            if heading:
                return self._prose_after_heading(heading, max_chars=3000)

        # Fallback: any region
        for region in self._get_all_content_regions(soup):
            heading = self._find_heading_in(region, ["估值", "valuation", "公允价值"])
            if heading:
                # Skip if it's in the TOC area (very short content after heading)
                text = self._prose_after_heading(heading, max_chars=3000)
                if len(text) > 200:  # Real content, not just a TOC entry
                    return text

        return ""

    # ── Helpers ────────────────────────────────────────────────────────

    def _find_heading_in(self, root: Tag, keywords: list[str]) -> Optional[Tag]:
        """Find the first heading (h1/h2/h3) in *root* matching any keyword."""
        for kw in keywords:
            for h in root.find_all(["h2", "h3", "h1"]):
                if kw.lower() in h.get_text(strip=True).lower():
                    return h
        return None

    def _prose_after_heading(self, heading: Tag, max_chars: int = 3000) -> str:
        """Extract prose text (paragraphs, lists) after a heading.

        Stops at the next heading of same or higher level.
        Tables are converted to Markdown rather than flattened.
        """
        level = int(heading.name[1]) if heading.name[0] == "h" else 2
        stop_tags = [f"h{i}" for i in range(1, level + 1)]

        parts = []
        total = 0
        for sib in heading.find_next_siblings():
            if not isinstance(sib, Tag):
                continue
            if sib.name in stop_tags:
                break
            if total >= max_chars:
                break

            if sib.name == "table":
                md = self._table_to_markdown(sib)
                parts.append(md)
                total += len(md)
            else:
                text = sib.get_text(separator="\n", strip=True)
                if text:
                    parts.append(text)
                    total += len(text)

        return "\n\n".join(parts)[:max_chars]

    def _section_prose(self, soup: BeautifulSoup, keywords: list[str]) -> str:
        """Search all content regions for a heading matching keywords, return prose."""
        for region in self._get_all_content_regions(soup):
            heading = self._find_heading_in(region, keywords)
            if heading:
                text = self._prose_after_heading(heading, max_chars=3000)
                if len(text) > 50:
                    return text
        return ""
