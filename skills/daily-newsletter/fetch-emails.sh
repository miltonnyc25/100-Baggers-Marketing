#!/bin/bash
# fetch-emails.sh - 获取今日 Grok 和 OpenAI 邮件

set -e

ACCOUNT="miltonnyc25@gmail.com"
OUTPUT_DIR="${1:-/tmp}"
DATE=$(date +%Y-%m-%d)

echo "📧 获取今日邮件 ($DATE)..."

# 获取 Grok 邮件
echo "🔍 搜索 Grok 邮件..."
gog gmail messages search "from:noreply@x.ai newer_than:1d" \
  --max 10 \
  --account "$ACCOUNT" \
  --json > "$OUTPUT_DIR/grok_emails.json" 2>/dev/null || echo "[]" > "$OUTPUT_DIR/grok_emails.json"

GROK_COUNT=$(jq '.messages | length // 0' "$OUTPUT_DIR/grok_emails.json" 2>/dev/null || echo "0")
echo "   找到 $GROK_COUNT 封 Grok 邮件"

# 获取 OpenAI 邮件
echo "🔍 搜索 OpenAI 邮件..."
gog gmail messages search "from:noreply@tm.openai.com newer_than:1d" \
  --max 20 \
  --account "$ACCOUNT" \
  --json > "$OUTPUT_DIR/openai_emails.json" 2>/dev/null || echo "[]" > "$OUTPUT_DIR/openai_emails.json"

OPENAI_COUNT=$(jq '.messages | length // 0' "$OUTPUT_DIR/openai_emails.json" 2>/dev/null || echo "0")
echo "   找到 $OPENAI_COUNT 封 OpenAI 邮件"

echo ""
echo "✅ 邮件数据已保存到:"
echo "   - $OUTPUT_DIR/grok_emails.json"
echo "   - $OUTPUT_DIR/openai_emails.json"
echo ""
echo "📊 汇总: Grok=$GROK_COUNT, OpenAI=$OPENAI_COUNT"
