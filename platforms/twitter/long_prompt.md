# X Long-Form Post — Translate Chinese Analysis to English

You are translating a Chinese-language stock analysis post into English for X (Twitter). The goal is a faithful, natural-sounding English version that preserves ALL content, data points, and analytical structure from the original.

## Source Material

Finished, quality-checked Chinese analysis about {company_name} (${ticker}):

--- BEGIN SOURCE ---
{xueqiu_content}
--- END SOURCE ---

## TRANSLATION GUIDELINES

1. **Faithful translation**: Preserve every data point, every argument, every analytical framework from the source. Do not omit, summarize, or re-order sections.

2. **Natural English**: The output must read as fluent, natural English — not as "translated Chinese." Restructure individual sentences as needed for English flow, but keep the overall structure intact.

3. **Financial term conversion**: Convert Chinese financial terms to their standard English equivalents naturally:
   - 营收 → revenue
   - 毛利率 → gross margin
   - 护城河 → moat / competitive advantage
   - 估值 → valuation
   - 自由现金流 → free cash flow
   - 市盈率 → P/E ratio
   - 企业价值/营收 → EV/Sales
   - 年复合增长率 → CAGR
   - 杀估值 → multiple compression
   - 戴维斯双杀 → Davis Double Play (multiple compression + earnings miss)

4. **Section separators**: Replace Chinese ——— separators with simple paragraph breaks. Do not add English headers or dividers.

5. **Ticker format**: Use ${ticker} cashtag where appropriate (2-4 times).

6. **Tone**: Maintain the analytical, data-driven tone of the original. The original was written for sophisticated investors; the English version should sound equally serious.

7. **Opening and closing**: Translate the hook and closing as-is. The Chinese post already has a strong opening and a probability-weighted framework at the end — preserve them.

8. **Numbers**: Keep ALL specific numbers exactly as they appear in the source. Do not round, approximate, or change any data.

9. **Chart/image references**: If the source mentions chart recommendations (配图建议), omit that section — it is metadata, not post content.

10. **Source link disclaimer**: If the source ends with "数据来源" or similar, translate it as:
    Data: https://www.100baggers.club/reports/{ticker_lower}

## ABSOLUTELY FORBIDDEN

- Fabricating data not in the source
- Omitting data points or arguments from the source
- Adding your own analysis or opinions not present in the source
- Price targets: "fair value is $X", "should trade at $X"
- Investment advice: "buy", "sell", "hold", "bullish", "bearish", "overvalued", "undervalued"
- AI-signal words: "delve", "landscape", "robust", "leveraging", "pivotal", "game-changer", "multifaceted", "nuanced", "navigate", "foster", "streamline", "embark", "comprehensive"
- Markdown formatting (no bold, no italics, no headers, no bullet lists)

## OUTPUT

Output ONLY the translated post text. No preamble, no explanation, no labels, no quotes. Plain text, ready to paste into X.
