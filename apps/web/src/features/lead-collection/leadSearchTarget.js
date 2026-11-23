const chineseDigits = {
  '零': 0,
  '一': 1,
  '二': 2,
  '两': 2,
  '三': 3,
  '四': 4,
  '五': 5,
  '六': 6,
  '七': 7,
  '八': 8,
  '九': 9,
};

const chineseUnits = { '十': 10, '百': 100, '千': 1000 };

function parseChineseInteger(text) {
  let total = 0;
  let current = 0;
  for (const char of text) {
    if (char in chineseDigits) {
      current = chineseDigits[char];
      continue;
    }
    const unit = chineseUnits[char];
    if (!unit) return null;
    total += (current || 1) * unit;
    current = 0;
  }
  return total + current;
}

export function parseLeadSearchTarget(text, maximum) {
  const arabic = text.match(/(\d+)\s*多?\s*[家个条]/);
  if (arabic) return Math.min(Number.parseInt(arabic[1], 10), maximum);

  const chinese = text.match(/([零一二两三四五六七八九十百千]+)\s*多?\s*[家个条]/);
  if (!chinese) return null;
  const value = parseChineseInteger(chinese[1]);
  return value == null ? null : Math.min(Math.max(value, 1), maximum);
}
