"""
Session state persistence.

Each review session is a JSON file in webapp/sessions/ tracking:
- ticker + platform selection
- segment list with generated content
- overall workflow status
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from engine.segment_schema import SegmentData

_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
_SESSIONS_DIR.mkdir(exist_ok=True)


@dataclass
class SessionState:
    session_id: str
    ticker: str
    platform: str
    created_at: str
    segments: list[SegmentData] = field(default_factory=list)
    overall_status: str = "splitting"  # splitting|generating|reviewing|approved|published

    # ── Video Curation Pipeline ───────────────────────────────────────
    video_angles: list = field(default_factory=list)       # Gemini-recommended angle dicts
    video_angles_status: str = "pending"                   # pending|generating|ready|failed
    selected_angle_index: int = -1                         # User's chosen angle (-1 = none)
    curated_document: str = ""                             # 30k+ char Gemini output
    curation_status: str = "pending"                       # pending|generating|ready|failed
    curated_video_path: str = ""                           # URL path to final video
    curated_video_status: str = "pending"                  # pending|generating|ready|failed
    curated_video_en_path: str = ""                        # English video URL path
    curated_video_en_status: str = "pending"               # pending|generating|ready|failed
    curated_xhs_post: str = ""                             # XHS post content (title + body)
    curated_publish_status: str = "pending"                # pending|publishing|published|failed

    # ── Persistence ──────────────────────────────────────────────────

    def save(self) -> Path:
        """Write session to JSON file."""
        path = _SESSIONS_DIR / f"{self.session_id}.json"
        data = {
            "session_id": self.session_id,
            "ticker": self.ticker,
            "platform": self.platform,
            "created_at": self.created_at,
            "overall_status": self.overall_status,
            "segments": [s.to_dict() for s in self.segments],
            # Video curation pipeline
            "video_angles": self.video_angles,
            "video_angles_status": self.video_angles_status,
            "selected_angle_index": self.selected_angle_index,
            "curated_document": self.curated_document,
            "curation_status": self.curation_status,
            "curated_video_path": self.curated_video_path,
            "curated_video_status": self.curated_video_status,
            "curated_video_en_path": self.curated_video_en_path,
            "curated_video_en_status": self.curated_video_en_status,
            "curated_xhs_post": self.curated_xhs_post,
            "curated_publish_status": self.curated_publish_status,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, session_id: str) -> Optional[SessionState]:
        """Load session from JSON file."""
        path = _SESSIONS_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            session_id=data["session_id"],
            ticker=data["ticker"],
            platform=data["platform"],
            created_at=data["created_at"],
            overall_status=data.get("overall_status", "reviewing"),
            segments=[SegmentData.from_dict(s) for s in data.get("segments", [])],
            # Video curation pipeline (backward-compatible defaults)
            video_angles=data.get("video_angles", []),
            video_angles_status=data.get("video_angles_status", "pending"),
            selected_angle_index=data.get("selected_angle_index", -1),
            curated_document=data.get("curated_document", ""),
            curation_status=data.get("curation_status", "pending"),
            curated_video_path=data.get("curated_video_path", ""),
            curated_video_status=data.get("curated_video_status", "pending"),
            curated_video_en_path=data.get("curated_video_en_path", ""),
            curated_video_en_status=data.get("curated_video_en_status", "pending"),
            curated_xhs_post=data.get("curated_xhs_post", ""),
            curated_publish_status=data.get("curated_publish_status", "pending"),
        )

    @classmethod
    def create(cls, ticker: str, platform: str) -> SessionState:
        """Create a new session with a generated ID."""
        return cls(
            session_id=uuid.uuid4().hex[:12],
            ticker=ticker.lower(),
            platform=platform.lower(),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )

    @classmethod
    def list_all(cls) -> list[SessionState]:
        """List all saved sessions, newest first."""
        sessions = []
        for path in sorted(_SESSIONS_DIR.glob("*.json"), reverse=True):
            try:
                s = cls.load(path.stem)
                if s:
                    sessions.append(s)
            except Exception:
                continue
        return sessions

    def delete(self) -> None:
        """Remove session file."""
        path = _SESSIONS_DIR / f"{self.session_id}.json"
        if path.exists():
            path.unlink()

    # ── Helpers ───────────────────────────────────────────────────────

    def segment_by_id(self, segment_id: str) -> Optional[SegmentData]:
        for s in self.segments:
            if s.segment_id == segment_id:
                return s
        return None

    def all_approved(self) -> bool:
        return all(s.status == "approved" for s in self.segments)

    def approved_count(self) -> int:
        return sum(1 for s in self.segments if s.status == "approved")

    def total_count(self) -> int:
        return len(self.segments)
