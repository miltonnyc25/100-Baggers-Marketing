"""
Path configuration and constants for the content extraction engine.
"""

from pathlib import Path
import os

# ── Report source paths ──────────────────────────────────────────────
REPORTS_DIR = Path(os.path.expanduser("~/Downloads/InvestView_v0/public/reports"))

# ── Production URLs ──────────────────────────────────────────────────
PRODUCTION_URL = "https://www.100baggers.club"
REPORT_URL_TEMPLATE = f"{PRODUCTION_URL}/reports/{{ticker}}"
COMPANY_URL_TEMPLATE = f"{PRODUCTION_URL}/reports/{{ticker}}"
EN_COMPANY_URL_TEMPLATE = f"{PRODUCTION_URL}/reports/{{ticker}}"

# ── API ──────────────────────────────────────────────────────────────
API_BASE_URL = f"{PRODUCTION_URL}/api"
GENERATE_SUMMARY_URL = f"{API_BASE_URL}/generate-summary"
COMPANY_REPORT_URL = f"{API_BASE_URL}/company/report"
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")

# ── Shared infrastructure (from clawd-workspace skills) ──────────────
CLAWD_SKILLS_DIR = Path(os.path.expanduser("~/clawd/skills"))
VENV_PYTHON = Path(os.path.expanduser("~/Downloads/add-caption/venv/bin/python"))
LOGO_PATH = Path(os.path.expanduser("~/Downloads/add-caption/assets/100bagersclub_logo.png"))
SOCIAL_UPLOADER_DIR = Path(os.path.expanduser("~/Downloads/add-caption/social_uploader"))

# ── AI model defaults ────────────────────────────────────────────────
GEMINI_MODEL = "gemini-3-pro-preview"

# ── Available report tickers ─────────────────────────────────────────
AVAILABLE_TICKERS = [
    "aapl", "amat", "amd", "amzn", "anet", "app", "asml", "cost",
    "etn", "googl", "klac", "lrcx", "meta", "msft", "mu", "orcl",
    "pg", "pltr", "rblx", "rddt", "smci", "sofi", "tsla", "tsm", "vrt",
]


def report_dir(ticker: str) -> Path:
    """Return the report directory for a given ticker."""
    return REPORTS_DIR / ticker.lower()


def find_markdown_report(ticker: str) -> Path | None:
    """Find the primary .md report file for a ticker (Chinese version)."""
    d = report_dir(ticker)
    if not d.exists():
        return None
    for f in sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.name != "README.md":
            return f
    return None


def find_english_markdown(ticker: str) -> Path | None:
    """Find the English .md report file for a ticker."""
    en_dir = report_dir(ticker) / "en"
    if not en_dir.exists():
        return None
    for f in sorted(en_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        return f
    return None


def find_html_report(ticker: str) -> Path | None:
    """Find the Chinese index.html report file for a ticker."""
    html = report_dir(ticker) / "index.html"
    return html if html.exists() else None


def find_english_html_report(ticker: str) -> Path | None:
    """Find the English index.html report file for a ticker."""
    html = report_dir(ticker) / "en" / "index.html"
    return html if html.exists() else None
