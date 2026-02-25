"""
Post-generation content filter.

Strips Mermaid diagrams, code blocks, and other banned content
from AI-generated output. Acts as a safety net when the model
ignores prompt instructions.
"""

from __future__ import annotations

import re


def strip_mermaid_and_code(text: str) -> str:
    """Remove all Mermaid diagrams and code blocks from generated text.

    Preserves JSON code blocks (needed for xiaohongshu/youtube output).
    """
    # Remove ```mermaid ... ``` blocks
    text = re.sub(r"```mermaid\s*\n.*?```", "", text, flags=re.DOTALL)

    # Remove ```graph / ```flowchart blocks
    text = re.sub(r"```(?:graph|flowchart|dot|plantuml)\s*\n.*?```", "", text, flags=re.DOTALL)

    # Remove generic code blocks (but keep ```json blocks)
    text = re.sub(r"```(?!json)[\w]*\s*\n.*?```", "", text, flags=re.DOTALL)

    # Remove inline mermaid-style graph definitions (no fences)
    text = re.sub(r"(?m)^graph\s+(?:TD|LR|TB|RL|BT)\s*\n(?:.*\n)*?(?=\n\S|\Z)", "", text)
    text = re.sub(r"(?m)^flowchart\s+(?:TD|LR|TB|RL|BT)\s*\n(?:.*\n)*?(?=\n\S|\Z)", "", text)

    # Remove ASCII art boxes (lines of dashes/pipes that look like diagrams)
    text = re.sub(r"(?m)^[│├└┌┐┘┤┬┴┼─]+.*$", "", text)
    text = re.sub(r"(?m)^\s*[+\-]{3,}\s*$", "", text)

    # Clean up multiple blank lines left by removals
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def strip_price_targets(text: str) -> str:
    """Remove explicit price target language from generated text."""
    # Chinese patterns — specific price conclusions
    text = re.sub(r"建议在?\$?[\d.]+[-–—~至到]\$?[\d.]+[^。]*(?:区间|仓位|观察)[^。]*[。]?", "", text)
    text = re.sub(r"目标价\$?[\d.]+[^。]*[。]?", "", text)
    text = re.sub(r"合理估值\s*(?:约|为|在)?\$?[\d.]+[^。]*[。]?", "", text)
    text = re.sub(r"公允价值\s*(?:约|区间|为|在)?\$?[\d.]+[^。]*[。]?", "", text)
    # "合理市值...被压缩至$211.7B（约合$265/股）" → strip the per-share price
    text = re.sub(r"[（(]约合?\$[\d.]+/股[）)]", "", text)
    # "在$260-290区间内波动" style ranges with dollar signs
    text = re.sub(r"在\$[\d.]+[-–—~至到]\$?[\d.]+(?:区间|之间)[^。]*", "", text)

    # English patterns
    text = re.sub(r"(?i)(?:fair value|target price|price target)\s*(?:of|is|at|:)?\s*\$[\d.]+[^.]*\.", "", text)
    text = re.sub(r"(?i)stock should trade (?:at|between) \$[\d.]+[^.]*\.", "", text)
    text = re.sub(r"(?i)\(\s*(?:approximately|roughly|about|~)\s*\$[\d.]+\s*/?\s*share\s*\)", "", text)

    # Clean up
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_markdown_formatting(text: str) -> str:
    """Remove markdown formatting markers (bold, italic, headers) from plain text output."""
    # Remove **bold** markers
    text = re.sub(r"\*{2}([^*]+?)\*{2}", r"\1", text)
    # Remove *italic* markers
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\1", text)
    # Remove markdown headers (# ## ###) but keep text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    return text


def clean_generated_content(text: str) -> str:
    """Apply all content filters to generated text."""
    text = strip_mermaid_and_code(text)
    text = strip_price_targets(text)
    text = strip_markdown_formatting(text)
    return text
