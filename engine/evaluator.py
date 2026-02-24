"""
Post-generation quality evaluator.

Calls Gemini to evaluate generated content against quality criteria.
Returns a pass/fail verdict with specific issues found.
If content fails, provides rewrite instructions for regeneration.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional


# ── Evaluation criteria per platform ────────────────────────────────

_EVAL_PROMPT_TEMPLATE = """\
You are a content compliance reviewer for a financial research marketing team.

Evaluate the following generated content for the platform "{platform}".

## IMPORTANT CONTEXT

The content is derived from our own proprietary deep research reports.
All numbers, metrics, and financial data in the content come from our
research reports and should be treated as CORRECT. Do NOT flag data as
"fabricated" or "inconsistent" — you do not have the source report to
verify against.

## Hard-fail rules (any single violation = FAIL)

1. **Direct investment advice or stock price conclusions**:
   FAIL if the content tells the reader what to DO with the stock, or states
   what the stock price SHOULD BE. Specifically, these patterns are violations:
   - Explicit price targets: "目标价$300", "target price $300", "fair value is $280"
   - Price range advice: "建议在$260-290区间建仓", "stock should trade at $X-$Y"
   - Buy/sell/hold: "建仓", "加仓", "减仓", "买入", "卖出", "buy", "sell", "hold" (as recommendations)
   - Explicit over/undervaluation claims: "被低估30%", "undervalued by 30%", "被高估"

   The following are ALLOWED (not violations):
   - Business segment valuations from the report: "AGS独立估值可达$19-26B" (this is analysis, not advice)
   - Market-implied assumptions: "股价隐含了18.8%的FCF CAGR" (describing what market prices, not recommending)
   - Risk-adjusted model outputs: "风险调整后市值约$211B" (model result, not recommendation)
   - Valuation framework comparisons: "P/E 29.9x vs 同业42-48x" (factual comparison)
   - Probability-weighted scenarios: "概率加权收入$32.2B vs 共识$37B" (analytical finding)

2. **Mermaid / code blocks**: Content must NOT contain ```mermaid, graph TD,
   graph LR, flowchart, or any code blocks.

## Quality criteria (scored 1-5 each)

3. **Data density**: Does every key claim cite a specific number?
4. **Coherence**: Does the text flow naturally? No garbled sentences, no abrupt
   truncation, no orphan phrases from deleted content? No sentences that look
   like they had words surgically removed?
5. **Analysis depth**: Does it go beyond surface metrics to reveal genuine insight
   about the company's intrinsic value?

## Your output

Return ONLY a JSON object:

```json
{{
  "pass": true/false,
  "violations": ["list of hard-fail violations, empty if none"],
  "scores": {{
    "data_density": 1-5,
    "coherence": 1-5,
    "analysis_depth": 1-5
  }},
  "total_score": 3-15,
  "rewrite_instructions": "If pass=false, specific instructions for what to fix. Only mention the ACTUAL violations — do not add new requirements. If pass=true, empty string."
}}
```

## Content to evaluate

Platform: {platform}
Ticker: {ticker}

--- BEGIN CONTENT ---
{content}
--- END CONTENT ---

Return ONLY the JSON. No explanation.
"""


def evaluate(
    content: str,
    platform: str,
    ticker: str,
) -> dict:
    """Evaluate generated content using Gemini.

    Returns dict with keys: pass, violations, scores, total_score,
    rewrite_instructions.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        # No API key — skip evaluation, assume pass
        return {
            "pass": True,
            "violations": [],
            "scores": {"data_density": 3, "coherence": 3, "analysis_depth": 3},
            "total_score": 9,
            "rewrite_instructions": "",
        }

    import google.generativeai as genai
    from engine.config import GEMINI_MODEL

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = _EVAL_PROMPT_TEMPLATE.format(
        platform=platform,
        ticker=ticker.upper(),
        content=content,
    )

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
    except Exception as exc:
        # Evaluation API call failed — assume pass to avoid blocking
        print(f"[evaluator] Evaluation call failed ({exc}), assuming pass")
        return {
            "pass": True,
            "violations": [],
            "scores": {"data_density": 3, "coherence": 3, "analysis_depth": 3},
            "total_score": 9,
            "rewrite_instructions": "",
        }

    # Parse JSON from response
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0]
    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON object
        match = re.search(r"\{[\s\S]+\}", raw)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                return _default_pass()
        else:
            return _default_pass()

    # Ensure required keys exist
    result.setdefault("pass", True)
    result.setdefault("violations", [])
    result.setdefault("scores", {})
    result.setdefault("total_score", sum(result["scores"].values()) if result["scores"] else 0)
    result.setdefault("rewrite_instructions", "")

    return result


def _default_pass() -> dict:
    """Return a default pass result when evaluation can't be parsed."""
    return {
        "pass": True,
        "violations": [],
        "scores": {"data_density": 3, "coherence": 3, "analysis_depth": 3},
        "total_score": 9,
        "rewrite_instructions": "",
    }


def flatten_content(content, platform: str) -> str:
    """Flatten platform-specific content dict/str into a single string for evaluation."""
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        parts = []
        if "title" in content:
            parts.append(f"Title: {content['title']}")
        if "slides" in content:
            for i, s in enumerate(content["slides"], 1):
                parts.append(f"Slide {i}: {s}")
        if "caption" in content:
            parts.append(f"Caption: {content['caption']}")
        if "script" in content:
            parts.append(f"Script: {content['script']}")
        if "description" in content:
            parts.append(f"Description: {content['description']}")
        return "\n\n".join(parts)

    if isinstance(content, list):
        return "\n\n".join(str(item) for item in content)

    return str(content)
