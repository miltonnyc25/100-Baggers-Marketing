"""
Data classes for report segments.

A SegmentData represents a thematic slice of a full report, grouping
related chapters for platform-specific content generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SegmentData:
    segment_id: str  # "seg1", "seg2", ...
    theme: str  # "executive_overview", "financial_deep_dive", etc.
    title: str  # Human-readable title
    source_chapter_ids: list[str] = field(default_factory=list)  # ["ch1", "ch2"]
    content_markdown: str = ""  # Combined chapter content
    tables: list[str] = field(default_factory=list)
    word_count: int = 0

    # Per-platform generated content: {"xueqiu": "...", "xiaohongshu": {...}}
    platform_content: dict = field(default_factory=dict)

    # Report screenshots (relative URLs to chart/table images)
    screenshots: list[str] = field(default_factory=list)

    # NotebookLM video
    video_path: str = ""
    video_status: str = "pending"  # pending | generating | processing | ready | failed

    # Review workflow
    status: str = "draft"  # draft | approved | published | rejected

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        return {
            "segment_id": self.segment_id,
            "theme": self.theme,
            "title": self.title,
            "source_chapter_ids": self.source_chapter_ids,
            "content_markdown": self.content_markdown,
            "tables": self.tables,
            "word_count": self.word_count,
            "platform_content": self.platform_content,
            "screenshots": self.screenshots,
            "video_path": self.video_path,
            "video_status": self.video_status,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SegmentData:
        """Deserialize from dict."""
        return cls(
            segment_id=d["segment_id"],
            theme=d["theme"],
            title=d["title"],
            source_chapter_ids=d.get("source_chapter_ids", []),
            content_markdown=d.get("content_markdown", ""),
            tables=d.get("tables", []),
            word_count=d.get("word_count", 0),
            platform_content=d.get("platform_content", {}),
            screenshots=d.get("screenshots", []),
            video_path=d.get("video_path", ""),
            video_status=d.get("video_status", "pending"),
            status=d.get("status", "draft"),
        )
