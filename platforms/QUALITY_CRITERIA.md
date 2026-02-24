# Content Quality Evaluation Criteria

Per-platform scoring rubric. Each criterion is 1-5 points. Total score = sum.

---

## Xueqiu (雪球) — 满分 30

| # | Criterion | 1 (Fail) | 3 (Pass) | 5 (Excellent) |
|---|-----------|----------|----------|---------------|
| 1 | **Data density** | <3 specific numbers | 5-8 numbers | Every sentence has a number |
| 2 | **Prose quality** | Table dumps / garbled text | Readable paragraphs | Fluid, professional prose |
| 3 | **Deep analysis** | Only surface metrics | Covers 2 value dimensions | Covers moat + outlook + assumptions + valuation |
| 4 | **No price targets** | Shows "$260-290" or "目标价" | Mentions valuation range vaguely | Purely framework-based, no price conclusions |
| 5 | **No Mermaid/code** | Contains ```mermaid or code blocks | Contains ASCII diagrams | Pure text, no diagrams |
| 6 | **Hook quality** | Generic opening | Interesting opening data point | Contrarian / surprising lead that stops the scroll |

**Minimum acceptable**: 18/30

---

## Xiaohongshu (小红书) — 满分 30

| # | Criterion | 1 (Fail) | 3 (Pass) | 5 (Excellent) |
|---|-----------|----------|----------|---------------|
| 1 | **Slide punch** | Generic / no data per slide | 3/5 slides have numbers | Every slide has a compelling data-point |
| 2 | **Title hook** | >20 chars or generic | Catchy, includes data | Irresistible, <20 chars, includes number |
| 3 | **Caption quality** | Table dumps / garbled | Structured with key takeaways | Polished, emoji numbers, CTA, hashtags |
| 4 | **Value analysis depth** | Only mentions price | Mentions moat or growth | Multi-dimension deep analysis |
| 5 | **No price targets** | Shows price range | Vague valuation mention | Framework only |
| 6 | **No Mermaid/code** | Contains code blocks | Minor formatting issues | Pure text + JSON only |

**Minimum acceptable**: 18/30

---

## Twitter/X — 满分 30

| # | Criterion | 1 (Fail) | 3 (Pass) | 5 (Excellent) |
|---|-----------|----------|----------|---------------|
| 1 | **Thread hook** | Generic | Good data point | Scroll-stopping contrarian insight |
| 2 | **Data per tweet** | <50% tweets have numbers | 70%+ have numbers | Every tweet has specific data |
| 3 | **280 char limit** | Multiple tweets over limit | 1 tweet over limit | All tweets under 280 chars |
| 4 | **Value analysis** | Surface metrics only | Covers 2 dimensions | Deep moat/outlook/valuation analysis |
| 5 | **No price targets** | Contains price predictions | Vague mention | No price language at all |
| 6 | **No Mermaid/code** | Contains code blocks | Minor issues | Plain text only |

**Minimum acceptable**: 18/30

---

## YouTube — 满分 35

| # | Criterion | 1 (Fail) | 3 (Pass) | 5 (Excellent) |
|---|-----------|----------|----------|---------------|
| 1 | **Script readability** | Reads like a report | Mostly conversational | Sounds natural when read aloud |
| 2 | **Data density** | <5 numbers in script | 10-15 numbers | 20+ specific data points |
| 3 | **Script length** | <500 or >3000 words | 650-1950 words | 800-1500 words (5-10 min) |
| 4 | **Value analysis depth** | Surface only | Covers 2 dimensions | Full moat/outlook/assumptions/valuation |
| 5 | **Visual cue markers** | No [SHOW:] markers | 3-5 markers | 8+ well-placed markers |
| 6 | **No price targets** | Contains targets | Vague mention | Framework analysis only |
| 7 | **No Mermaid/code** | Contains code blocks | Minor issues | Clean JSON output |

**Minimum acceptable**: 21/35

---

## Automated Check (run after generation)

Quick pass/fail checks that can be automated:

```python
def quick_quality_check(text: str, platform: str) -> dict:
    issues = []
    # Hard fail: Mermaid
    if '```mermaid' in text or 'graph TD' in text or 'graph LR' in text:
        issues.append("FAIL: Contains Mermaid diagram")
    # Hard fail: code blocks
    if '```' in text and platform != 'youtube':  # youtube returns JSON
        issues.append("FAIL: Contains code block")
    # Hard fail: price targets
    import re
    if re.search(r'目标价|target price|fair value.{0,10}\$\d|应该在\$?\d+.*区间', text, re.I):
        issues.append("FAIL: Contains price target")
    # Warning: too short
    if len(text) < 500:
        issues.append("WARN: Content too short (<500 chars)")
    # Warning: no numbers
    numbers = re.findall(r'\d+\.?\d*[%xBMK]', text)
    if len(numbers) < 3:
        issues.append("WARN: Very few data points (<3)")
    return {"pass": len([i for i in issues if i.startswith("FAIL")]) == 0, "issues": issues}
```
