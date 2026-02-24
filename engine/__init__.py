"""
100Baggers Report Content Extraction Engine

Parses deep research reports (Markdown / HTML) into structured ReportData
for downstream platform content generators.
"""

from engine.report_schema import ReportData, ReportMetadata, ChapterContent
from engine.segment_schema import SegmentData
from engine.config import REPORTS_DIR, PRODUCTION_URL, VENV_PYTHON
from engine.markdown_parser import MarkdownReportParser
from engine.report_parser import HTMLReportParser
from engine.segment_splitter import SegmentSplitter
from engine.segment_generator import generate_segment_content, generate_all_segments

__all__ = [
    "ReportData",
    "ReportMetadata",
    "ChapterContent",
    "SegmentData",
    "MarkdownReportParser",
    "HTMLReportParser",
    "SegmentSplitter",
    "generate_segment_content",
    "generate_all_segments",
    "REPORTS_DIR",
    "PRODUCTION_URL",
    "VENV_PYTHON",
]
