"""CLI 子命令测试。"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from vigi import cli, days, parser, projects, storage


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        storage.ensure_data_dirs(self.data_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def base(self, *rest: str) -> list[str]:
        return ["--dir", str(self.data_dir), *rest]


class SmokeTests(CliTestCase):
    def test_no_subcommand_needs_tty(self) -> None:
        # 测试环境非交互式终端，应给出提示并返回 1，而不是崩溃
        code, out, _ = run_cli(*self.base())
        self.assertEqual(code, 1)
        self.assertIn("TUI", out)

    def test_version(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)


class ProjectCommandTests(CliTestCase):
    def test_new_creates_project(self) -> None:
        code, out, _ = run_cli(
            *self.base("new", "Frankfurt HPS", "--id", "frankfurt-hps", "--stage", "重写")
        )
        self.assertEqual(code, 0)
        self.assertIn("frankfurt-hps", out)
        self.assertTrue(
            storage.project_path(self.data_dir, "frankfurt-hps").is_file()
        )

    def test_new_invalid_deadline_exit_2(self) -> None:
        code, _, err = run_cli(
            *self.base("new", "T", "--id", "t", "--deadline", "2026/01/01")
        )
        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM-DD", err)

    def test_new_duplicate_exit_1(self) -> None:
        run_cli(*self.base("new", "T", "--id", "t"))
        code, _, err = run_cli(*self.base("new", "T", "--id", "t"))
        self.assertEqual(code, 1)
        self.assertIn("已存在", err)

    def test_projects_lists(self) -> None:
        run_cli(*self.base("new", "Frankfurt HPS", "--id", "frankfurt-hps"))
        code, out, _ = run_cli(*self.base("projects"))
        self.assertEqual(code, 0)
        self.assertIn("frankfurt-hps", out)
        self.assertIn("进行中", out)

    def test_projects_empty(self) -> None:
        code, out, _ = run_cli(*self.base("projects"))
        self.assertEqual(code, 0)
        self.assertIn("没有项目", out)

    def test_current_and_next(self) -> None:
        run_cli(*self.base("new", "T", "--id", "t"))
        code, out, _ = run_cli(*self.base("current", "t", "改写导论。"))
        self.assertEqual(code, 0)
        self.assertIn("当前", out)
        code, out, _ = run_cli(*self.base("next", "t", "接 Neurath。"))
        self.assertEqual(code, 0)
        self.assertIn("下一步", out)
        project = parser.parse_project(
            storage.read_text(storage.project_path(self.data_dir, "t")), "t"
        )
        self.assertEqual(project.current, "改写导论。")
        self.assertEqual(project.next, "接 Neurath。")

    def test_current_can_be_cleared(self) -> None:
        run_cli(*self.base("new", "T", "--id", "t"))
        run_cli(*self.base("current", "t", "X"))
        run_cli(*self.base("current", "t", ""))
        project = parser.parse_project(
            storage.read_text(storage.project_path(self.data_dir, "t")), "t"
        )
        self.assertEqual(project.current, "")

    def test_current_unknown_project_exit_1(self) -> None:
        code, _, err = run_cli(*self.base("current", "nope", "X"))
        self.assertEqual(code, 1)
        self.assertIn("找不到项目", err)


class TouchFocusCommandTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        run_cli(*self.base("new", "Frankfurt HPS", "--id", "frankfurt-hps"))

    def test_touch(self) -> None:
        code, out, _ = run_cli(*self.base("touch", "frankfurt-hps", "-m", "推进第二节"))
        self.assertEqual(code, 0)
        self.assertIn("已推进", out)
        project = parser.parse_project(
            storage.read_text(storage.project_path(self.data_dir, "frankfurt-hps")),
            "frankfurt-hps",
        )
        self.assertEqual(project.log[0].note, "推进第二节")

    def test_touch_unknown_gives_suggestion(self) -> None:
        code, _, err = run_cli(*self.base("touch", "frankfrut-hps"))
        self.assertEqual(code, 1)
        self.assertIn("找不到项目", err)
        self.assertIn("frankfurt-hps", err)

    def test_focus(self) -> None:
        code, out, _ = run_cli(*self.base("focus", "frankfurt-hps"))
        self.assertEqual(code, 0)
        self.assertIn("今日重点", out)
        record = parser.parse_day(
            storage.read_text(storage.day_path(self.data_dir, date.today())),
            date.today(),
        )
        self.assertEqual(record.focus, "frankfurt-hps")


class InfoCommandTests(CliTestCase):
    def test_info_shows_version(self) -> None:
        from vigi import __version__

        _, out, _ = run_cli(*self.base("info"))
        self.assertIn(__version__, out)

    def test_info_shows_dir_and_cli_source(self) -> None:
        code, out, _ = run_cli(*self.base("info"))
        self.assertEqual(code, 0)
        self.assertIn("数据目录", out)
        self.assertIn(str(self.data_dir), out)
        self.assertIn("--dir", out)

    def test_info_env_source(self) -> None:
        with mock.patch.dict(os.environ, {"vigi_DIR": str(self.data_dir)}):
            code, out, _ = run_cli("info")
        self.assertEqual(code, 0)
        self.assertIn("环境变量", out)
        self.assertIn(str(self.data_dir), out)

    def test_info_does_not_create_dir(self) -> None:
        target = Path(self._tmp.name) / "unused"
        with mock.patch.dict(os.environ, {"vigi_DIR": str(target)}):
            run_cli("info")
        self.assertFalse(target.exists())


class NoteCommandTests(CliTestCase):
    def test_note_then_today(self) -> None:
        code, out, _ = run_cli(*self.base("note", "写点东西"))
        self.assertEqual(code, 0)
        self.assertIn("写点东西", out)
        _, out2, _ = run_cli(*self.base("today"))
        self.assertIn("写点东西", out2)

    def test_note_empty_rejected(self) -> None:
        code, _, err = run_cli(*self.base("note", "   "))
        self.assertEqual(code, 2)
        self.assertIn("不能为空", err)


class ArgOrderTests(CliTestCase):
    def test_dir_after_subcommand(self) -> None:
        run_cli("new", "AfterDir", "--id", "aft", "--dir", str(self.data_dir))
        code, out, _ = run_cli("projects", "--dir", str(self.data_dir))
        self.assertEqual(code, 0)
        self.assertIn("AfterDir", out)

    def test_edit_nonzero_exit_becomes_1(self) -> None:
        run_cli(*self.base("new", "T", "--id", "t"))
        with mock.patch.dict(os.environ, {"EDITOR": "false"}):
            code, _, _ = run_cli(*self.base("edit", "t"))
        self.assertEqual(code, 1)


class ArchiveDeleteCommandTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        run_cli(*self.base("new", "A", "--id", "a"))

    def test_archive(self) -> None:
        code, out, _ = run_cli(*self.base("archive", "a"))
        self.assertEqual(code, 0)
        self.assertIn("已归档", out)
        self.assertFalse(storage.project_path(self.data_dir, "a").is_file())

    def test_delete_with_yes(self) -> None:
        code, out, _ = run_cli(*self.base("delete", "a", "--yes"))
        self.assertEqual(code, 0)
        self.assertIn("已删除", out)
        self.assertFalse(storage.project_path(self.data_dir, "a").is_file())

    def test_delete_cancelled(self) -> None:
        with mock.patch("builtins.input", return_value="n"):
            code, out, _ = run_cli(*self.base("delete", "a"))
        self.assertEqual(code, 0)
        self.assertIn("已取消", out)
        self.assertTrue(storage.project_path(self.data_dir, "a").is_file())

    def test_delete_confirmed(self) -> None:
        with mock.patch("builtins.input", return_value="y"):
            code, _, _ = run_cli(*self.base("delete", "a"))
        self.assertEqual(code, 0)
        self.assertFalse(storage.project_path(self.data_dir, "a").is_file())

    def test_delete_clears_today_focus(self) -> None:
        run_cli(*self.base("focus", "a"))
        run_cli(*self.base("delete", "a", "--yes"))
        self.assertIsNone(days.load_day(self.data_dir, date.today()).focus)

    def test_unarchive(self) -> None:
        run_cli(*self.base("archive", "a"))
        code, out, _ = run_cli(*self.base("unarchive", "a"))
        self.assertEqual(code, 0)
        self.assertIn("已取消归档", out)
        self.assertTrue(storage.project_path(self.data_dir, "a").is_file())

    def test_projects_archived_listing(self) -> None:
        run_cli(*self.base("archive", "a"))
        code, out, _ = run_cli(*self.base("projects", "--archived"))
        self.assertEqual(code, 0)
        self.assertIn("归档", out)
        self.assertIn("a", out)


class FocusCommandTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        run_cli(*self.base("new", "A", "--id", "a"))

    def test_focus_set_and_clear(self) -> None:
        run_cli(*self.base("focus", "a"))
        self.assertEqual(days.load_day(self.data_dir, date.today()).focus, "a")
        code, out, _ = run_cli(*self.base("focus", "--clear"))
        self.assertEqual(code, 0)
        self.assertIn("已清除", out)
        self.assertIsNone(days.load_day(self.data_dir, date.today()).focus)

    def test_focus_without_id_errors(self) -> None:
        code, _, err = run_cli(*self.base("focus"))
        self.assertEqual(code, 2)
        self.assertIn("--clear", err)


class ReviewAllCommandTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        run_cli(*self.base("new", "A", "--id", "a"))
        run_cli(*self.base("new", "B", "--id", "b"))
        projects.set_status(self.data_dir, "b", "paused")

    def test_review_all_flag(self) -> None:
        code, out, _ = run_cli(*self.base("review", "--all"))
        self.assertEqual(code, 0)
        self.assertIn("项目回顾（全部）", out)
        self.assertIn("已暂停", out)

    def test_review_default_hides_paused(self) -> None:
        _, out, _ = run_cli(*self.base("review"))
        self.assertNotIn("已暂停", out)


class TodayCommandTests(CliTestCase):
    def test_today_shows_focus_routine_and_notes(self) -> None:
        run_cli(*self.base("new", "Frankfurt HPS", "--id", "frankfurt-hps"))
        run_cli(*self.base("focus", "frankfurt-hps"))
        run_cli(*self.base("done", "reading"))
        days.append_note(self.data_dir, date.today(), "今天状态一般")

        code, out, _ = run_cli(*self.base("today"))
        self.assertEqual(code, 0)
        self.assertIn("今日记录", out)
        self.assertIn("Frankfurt HPS", out)
        self.assertIn("阅读", out)
        self.assertIn("今天状态一般", out)

    def test_today_without_notes(self) -> None:
        code, out, _ = run_cli(*self.base("today"))
        self.assertEqual(code, 0)
        self.assertIn("备注", out)
        self.assertIn("（无）", out)

    def test_today_does_not_create_file(self) -> None:
        run_cli(*self.base("today"))
        self.assertFalse(storage.day_path(self.data_dir, date.today()).exists())


class RoutineAndReviewCommandTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        run_cli(*self.base("new", "Frankfurt HPS", "--id", "frankfurt-hps"))
        run_cli(*self.base("touch", "frankfurt-hps"))

    def test_done_then_undo(self) -> None:
        code, out, _ = run_cli(*self.base("done", "reading"))
        self.assertEqual(code, 0)
        self.assertIn("已打卡", out)
        code, out, _ = run_cli(*self.base("undo", "reading"))
        self.assertEqual(code, 0)
        self.assertIn("已取消", out)

    def test_invalid_routine_exit_2(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            cli.main(self.base("done", "cooking"))
        self.assertEqual(ctx.exception.code, 2)

    def test_review(self) -> None:
        code, out, _ = run_cli(*self.base("review"))
        self.assertEqual(code, 0)
        self.assertIn("项目回顾", out)
        self.assertIn("Frankfurt HPS", out)

    def test_review_week(self) -> None:
        code, out, _ = run_cli(*self.base("review", "--week"))
        self.assertEqual(code, 0)
        self.assertIn("周", out)
        self.assertIn("例行事项", out)


if __name__ == "__main__":
    unittest.main()
