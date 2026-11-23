"""Text normalization: convert Traditional Chinese → Simplified Chinese.

Prioritizes OpenCC (opencc-python-reimplemented) with a fallback
character-mapping table (~100 common pairs) when OpenCC is not installed.
"""

from __future__ import annotations

from typing import Any

# Fallback: common Traditional → Simplified character pairs
_TRAD_TO_SIMP_MAP: dict[int, int] = {}
_FALLBACK_TABLE: dict[str, str] = {
    "會": "会", "體": "体", "個": "个", "們": "们", "來": "来",
    "對": "对", "動": "动", "學": "学", "實": "实", "開": "开",
    "關": "关", "時": "时", "現": "现", "發": "发", "當": "当",
    "過": "过", "還": "还", "後": "后", "說": "说", "為": "为",
    "與": "与", "從": "从", "經": "经", "種": "种", "沒": "没",
    "這": "这", "業": "业", "機": "机", "點": "点", "問": "问",
    "進": "进", "長": "长", "門": "门", "間": "间", "隊": "队",
    "頭": "头", "萬": "万", "話": "话", "寫": "写", "應": "应",
    "場": "场", "報": "报", "結": "结", "給": "给", "氣": "气",
    "車": "车", "電": "电", "風": "风", "馬": "马", "魚": "鱼",
    "買": "买", "賣": "卖", "見": "见", "覺": "觉", "計": "计",
    "讓": "让", "認": "认", "語": "语", "請": "请", "謝": "谢",
    "資": "资", "質": "质", "費": "费", "買": "买", "賣": "卖",
    "遠": "远", "連": "连", "運": "运", "達": "达", "選": "选",
    "醫": "医", "護": "护", "軍": "军", "農": "农", "銀": "银",
    "錢": "钱", "鐵": "铁", "難": "难", "雲": "云", "電": "电",
    "飯": "饭", "飲": "饮", "飛": "飞", "館": "馆", "驗": "验",
    "體": "体", "處": "处", "術": "术", "備": "备", "勝": "胜",
    "勞": "劳", "務": "务", "勢": "势", "動": "动", "匯": "汇",
    "區": "区", "協": "协", "卻": "却", "員": "员", "單": "单",
    "參": "参", "嗎": "吗", "劉": "刘", "張": "张", "楊": "杨",
    "趙": "赵", "陳": "陈", "黃": "黄", "吳": "吴", "會": "会",
    "議": "议", "錄": "录", "項": "项", "紀": "纪", "總": "总",
    "結": "结", "記": "记", "劃": "划", "際": "际", "標": "标",
    "內": "内", "容": "容", "匯": "汇",
}
# Deduplicate — dict picks the last value for duplicate keys
_FALLBACK_TABLE_DEDUPED: dict[str, str] = {}
for _k, _v in _FALLBACK_TABLE.items():
    _FALLBACK_TABLE_DEDUPED[_k] = _v
_FALLBACK_TABLE = _FALLBACK_TABLE_DEDUPED
for _k, _v in _FALLBACK_TABLE.items():
    _TRAD_TO_SIMP_MAP[ord(_k)] = ord(_v)
_FALLBACK_TRANSLATION = str.maketrans(_TRAD_TO_SIMP_MAP)  # type: ignore[arg-type]


# Attempt to load OpenCC for a higher-quality conversion.
_OPENCC = None
try:
    from opencc import OpenCC  # type: ignore[import-untyped]

    _OPENCC = OpenCC("t2s")
except Exception:  # pragma: no cover — optional dependency
    pass


def to_simplified_text(text: str) -> str:
    """Convert *text* from Traditional Chinese to Simplified Chinese."""
    if _OPENCC is not None:
        return _OPENCC.convert(text)
    return text.translate(_FALLBACK_TRANSLATION)


def normalize_to_simplified(value: Any) -> Any:
    """Recursively convert all strings in `value` to simplified Chinese."""
    if isinstance(value, str):
        return to_simplified_text(value)
    if isinstance(value, list):
        return [normalize_to_simplified(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_to_simplified(item) for item in value)
    if isinstance(value, dict):
        return {k: normalize_to_simplified(v) for k, v in value.items()}
    return value
