"""终端显示宽度辅助：按东亚宽字符计算列宽，供 TUI 与 CLI 共用。"""

from __future__ import annotations

import unicodedata

_WIDE = ("W", "F")


def char_width(ch: str) -> int:
    """单个字符在终端中的显示宽度（CJK 宽字符为 2）。"""
    return 2 if unicodedata.east_asian_width(ch) in _WIDE else 1


def display_width(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def truncate(text: str, width: int) -> str:
    """按显示宽度截断，绝不切断宽字符。"""
    if width <= 0:
        return ""
    out: list[str] = []
    used = 0
    for ch in text:
        size = char_width(ch)
        if used + size > width:
            break
        out.append(ch)
        used += size
    return "".join(out)


def truncate_left(text: str, width: int) -> str:
    """从左侧截断，保留末尾 ``width`` 列（用于单行输入框显示光标附近）。"""
    if width <= 0:
        return ""
    out: list[str] = []
    used = 0
    for ch in reversed(text):
        size = char_width(ch)
        if used + size > width:
            break
        out.append(ch)
        used += size
    return "".join(reversed(out))


def pad(text: str, width: int) -> str:
    """按显示宽度右侧补空格。"""
    text = truncate(text, width)
    return text + " " * (width - display_width(text))
