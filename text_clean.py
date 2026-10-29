"""Turn emoji and messy spacing into text a Cantonese voice can read."""

from __future__ import annotations

import re

# Spoken stand-ins. The Hong Kong neural voices skip emoji instead of reading them.
EMOJI_WORDS = {
    "🤣": "大笑",
    "😂": "笑",
    "😀": "開心",
    "😃": "開心",
    "😄": "開心",
    "😁": "開心",
    "😊": "微笑",
    "😉": "眨眼",
    "😍": "好鍾意",
    "🥰": "好鍾意",
    "😘": "親一親",
    "😭": "大喊",
    "😢": "喊",
    "😡": "好嬲",
    "😠": "嬲",
    "😱": "驚",
    "😅": "尷尬笑",
    "🤔": "諗緊",
    "😴": "眼訓",
    "😎": "好得意",
    "😤": "唔抵",
    "💀": "嚇死",
    "🙈": "唔好睇",
    "👍": "讚",
    "👎": "唔好",
    "👏": "拍手",
    "🙏": "多謝",
    "💪": "加油",
    "👀": "睇住",
    "🤝": "合作",
    "❤️": "心",
    "❤": "心",
    "💕": "心",
    "💖": "心",
    "💗": "心",
    "🔥": "好勁",
    "⭐": "星星",
    "🌟": "星星",
    "✅": "完成",
    "❌": "唔得",
    "⚠️": "注意",
    "⚠": "注意",
    "❗": "注意",
    "❓": "問號",
    "💯": "一百分",
    "🎉": "慶祝",
    "🥳": "慶祝",
    "📌": "重點",
    "📝": "筆記",
    "📢": "公佈",
    "💡": "提示",
    "🚀": "快",
    "💰": "錢",
    "📈": "上升",
    "📉": "下跌",
}

_LEFTOVER_EMOJI = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F3FB-\U0001F3FF"
    "\u200d"
    "\ufe0e"
    "\ufe0f"
    "\u20e3"
    "]+"
)


def prepare_spoken_text(text: str) -> tuple[str, int]:
    """Replace known emoji with words, drop the rest, and tidy spacing."""
    changed = 0
    cleaned = text.replace("\ufe0f", "").replace("\ufe0e", "")
    for emoji, word in EMOJI_WORDS.items():
        key = emoji.replace("\ufe0f", "").replace("\ufe0e", "")
        count = cleaned.count(key)
        if count:
            cleaned = cleaned.replace(key, word)
            changed += count

    def _drop(match: re.Match[str]) -> str:
        nonlocal changed
        changed += 1
        return ""

    cleaned = _LEFTOVER_EMOJI.sub(_drop, cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([，。！？、；：,.!?])", r"\1", cleaned)
    return cleaned.strip(), changed
