"""TUI 宽字符辅助函数测试。

curses 交互本身不做自动化测试（TUI 自动化不是重点），
但宽度计算与截断必须可测试。
"""

from __future__ import annotations

import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from vigi import projects, storage, tui


class WidthTests(unittest.TestCase):
    def test_ascii_width(self) -> None:
        self.assertEqual(tui.display_width("abc"), 3)

    def test_cjk_width(self) -> None:
        self.assertEqual(tui.display_width("中文"), 4)

    def test_mixed_width(self) -> None:
        self.assertEqual(tui.display_width("a中b"), 4)

    def test_char_width(self) -> None:
        self.assertEqual(tui.char_width("a"), 1)
        self.assertEqual(tui.char_width("中"), 2)


class TruncateTests(unittest.TestCase):
    def test_no_truncation_needed(self) -> None:
        self.assertEqual(tui.truncate("abc", 10), "abc")

    def test_truncate_ascii(self) -> None:
        self.assertEqual(tui.truncate("abcdef", 3), "abc")

    def test_truncate_never_splits_cjk(self) -> None:
        # "中文" 宽 4；宽度 3 只能放下一个宽字符
        self.assertEqual(tui.truncate("中文", 3), "中")
        self.assertEqual(tui.truncate("中文", 2), "中")
        self.assertEqual(tui.truncate("中文", 1), "")

    def test_zero_or_negative(self) -> None:
        self.assertEqual(tui.truncate("abc", 0), "")
        self.assertEqual(tui.truncate("abc", -1), "")


class PadTests(unittest.TestCase):
    def test_pad_ascii(self) -> None:
        self.assertEqual(tui.pad("ab", 4), "ab  ")

    def test_pad_cjk_accounts_for_width(self) -> None:
        # "中" 宽 2，总宽 4 → 补 2 个空格
        self.assertEqual(tui.pad("中", 4), "中  ")

    def test_pad_truncates_when_too_long(self) -> None:
        self.assertEqual(tui.pad("abcdef", 3), "abc")


class EditRefreshTests(unittest.TestCase):
    """用 $EDITOR 编辑文件后，首页数据必须被标记为需要重载。"""

    @staticmethod
    def _app():
        stdscr = types.SimpleNamespace(
            keypad=lambda *a, **k: None, refresh=lambda *a, **k: None
        )
        return tui.App(stdscr, "/tmp")

    def _run_edit(self, side_effect=None):
        app = self._app()
        app.dirty = False
        with mock.patch.object(tui.curses, "def_prog_mode"), mock.patch.object(
            tui.curses, "endwin"
        ), mock.patch.object(tui.curses, "reset_prog_mode"), mock.patch.object(
            tui.subprocess, "call", side_effect=side_effect, return_value=0
        ), mock.patch.dict(os.environ, {"EDITOR": "true"}):
            app._edit_path("/tmp/whatever.md")
        return app

    def test_edit_marks_dirty(self) -> None:
        self.assertTrue(self._run_edit().dirty)

    def test_editor_failure_is_handled_and_marks_dirty(self) -> None:
        app = self._run_edit(side_effect=FileNotFoundError)
        self.assertTrue(app.dirty)
        self.assertTrue(app.message)


class HomeLoadTests(unittest.TestCase):
    """首页数据加载：空列表下标、以及“全部项目”过滤。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        storage.ensure_data_dirs(self.data_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _app(data_dir):
        stdscr = types.SimpleNamespace(
            keypad=lambda *a, **k: None, refresh=lambda *a, **k: None
        )
        return tui.App(stdscr, str(data_dir))

    def test_empty_list_keeps_index_zero(self) -> None:
        app = self._app(self.data_dir)
        app.index = 5
        app._load_home()
        self.assertEqual(app.projects, [])
        self.assertEqual(app.index, 0)

    def test_show_all_includes_non_active(self) -> None:
        projects.create_project(self.data_dir, "a", "A")
        projects.create_project(self.data_dir, "b", "B", status="paused")
        app = self._app(self.data_dir)
        app._load_home()
        self.assertEqual([p.project_id for p in app.projects], ["a"])
        app.show_all = True
        app._load_home()
        self.assertEqual({p.project_id for p in app.projects}, {"a", "b"})


class WindowTests(unittest.TestCase):
    def test_no_scroll_needed(self) -> None:
        self.assertEqual(tui.App._window(3, 1, 10), (0, 3))

    def test_scrolls_to_keep_selection_visible(self) -> None:
        self.assertEqual(tui.App._window(20, 15, 5), (11, 16))

    def test_clamps_near_end(self) -> None:
        self.assertEqual(tui.App._window(20, 19, 5), (15, 20))

    def test_empty(self) -> None:
        self.assertEqual(tui.App._window(0, 0, 5), (0, 0))


class ConfirmTests(unittest.TestCase):
    def _app(self, key):
        stdscr = types.SimpleNamespace(
            getmaxyx=lambda: (24, 80),
            addstr=lambda *a, **k: None,
            refresh=lambda *a, **k: None,
            keypad=lambda *a, **k: None,
        )
        app = tui.App(stdscr, "/tmp")
        app._get_key = lambda: key
        return app

    def test_yes(self) -> None:
        self.assertTrue(self._app("y")._confirm("x"))

    def test_no(self) -> None:
        self.assertFalse(self._app("n")._confirm("x"))

    def test_eof(self) -> None:
        self.assertFalse(self._app("EOF")._confirm("x"))


if __name__ == "__main__":
    unittest.main()
