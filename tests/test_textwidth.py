"""显示宽度辅助与回顾表格对齐的测试。"""

from __future__ import annotations

import unittest

from vigi import ui_text
from vigi.textwidth import (
    char_width,
    display_width,
    pad,
    truncate,
    truncate_left,
)


class WidthTests(unittest.TestCase):
    def test_ascii_and_cjk(self) -> None:
        self.assertEqual(display_width("abc"), 3)
        self.assertEqual(display_width("中文"), 4)
        self.assertEqual(display_width("a中b"), 4)

    def test_char_width(self) -> None:
        self.assertEqual(char_width("a"), 1)
        self.assertEqual(char_width("中"), 2)


class TruncatePadTests(unittest.TestCase):
    def test_truncate_never_splits_cjk(self) -> None:
        self.assertEqual(truncate("中文", 3), "中")
        self.assertEqual(truncate("中文", 1), "")
        self.assertEqual(truncate("abc", 0), "")

    def test_pad_by_display_width(self) -> None:
        self.assertEqual(pad("中", 4), "中  ")
        self.assertEqual(display_width(pad("中文", 6)), 6)

    def test_truncate_left_keeps_tail(self) -> None:
        self.assertEqual(truncate_left("abcdef", 3), "def")
        self.assertEqual(truncate_left("abc", 10), "abc")
        self.assertEqual(truncate_left("abc", 0), "")
        self.assertEqual(truncate_left("中文", 3), "文")


class ReviewTableTests(unittest.TestCase):
    def test_every_line_has_equal_display_width(self) -> None:
        rows = [
            ("短标题", "今天", 4, 13, "进行中"),
            ("一个明显更长的项目标题", "12 天前 !", 0, 3, "想法"),
        ]
        lines = ui_text.format_review_table(rows, width=60)
        self.assertEqual(display_width(lines[0]), display_width(lines[1]))
        widths = {display_width(line) for line in lines}
        self.assertEqual(len(widths), 1, lines)

    def test_columns_start_at_same_position(self) -> None:
        rows = [
            ("A", "今天", 1, 2, "进行中"),
            ("中文标题", "从未 !", 0, 0, "已暂停"),
        ]
        lines = ui_text.format_review_table(rows, width=60)
        # 表头与数据行的“最近”列应起于同一显示列
        header, first, second = lines[0], lines[1], lines[2]
        self.assertEqual(
            _column_start(header, "最近"), _column_start(first, "今天")
        )
        self.assertEqual(
            _column_start(header, "最近"), _column_start(second, "从未")
        )


    def test_projects_table_aligned(self) -> None:
        rows = [
            ("irrigation-history", "山区村落的灌溉系统", "进行中", "今天"),
            ("x", "短", "想法", "12 天前"),
        ]
        lines = ui_text.format_projects_table(rows, width=70)
        widths = {display_width(line) for line in lines}
        self.assertEqual(len(widths), 1, lines)


class HelpLayoutTests(unittest.TestCase):
    def test_description_column_aligned(self) -> None:
        lines = ui_text.tui_help_lines()
        key_w = max(display_width(key) for key, _ in ui_text.TUI_HELP if key)
        for key, desc in ui_text.TUI_HELP:
            if not desc:
                continue
            expected = pad(key, key_w) + "  " + desc
            self.assertIn(expected, lines)
            prefix = expected[: expected.index(desc)]
            self.assertEqual(display_width(prefix), key_w + 2, expected)


def _column_start(line: str, token: str) -> int:
    return display_width(line[: line.index(token)])


if __name__ == "__main__":
    unittest.main()
