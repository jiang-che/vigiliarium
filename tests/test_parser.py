"""解析与保守写回的单元测试。"""

from __future__ import annotations

import unittest
from datetime import date

from vigi import parser
from vigi.models import ROUTINES

PROJECT = """# Frankfurt School and Early HPS

Status: active
Stage: 重写
Deadline: 2026-11-30

## Current

重写第二节。

## Next

处理 Horkheimer 与 HPS 之间的关系。

## Log

- 2026-10-01 — 推进第二节，Horkheimer 部分基本成形。
- 2026-09-30 — 重新整理第二节论证。
- 2026-09-27 — 查阅 Grossmann 与 Horkheimer 材料。
"""

DAY = """# 2026-10-01

Focus: frankfurt-hps

## Routine

- [x] Reading
- [x] Writing
- [ ] Email
- [ ] Admin

## Projects

- [x] frankfurt-hps

## Notes

- Frankfurt HPS：第二节继续推进。
"""


class ParseProjectTests(unittest.TestCase):
    def test_normal(self) -> None:
        project = parser.parse_project(PROJECT, "frankfurt-hps")
        self.assertEqual(project.title, "Frankfurt School and Early HPS")
        self.assertEqual(project.status, "active")
        self.assertEqual(project.stage, "重写")
        self.assertEqual(project.deadline, date(2026, 11, 30))
        self.assertEqual(project.current, "重写第二节。")
        self.assertEqual(project.next, "处理 Horkheimer 与 HPS 之间的关系。")
        self.assertEqual(len(project.log), 3)
        self.assertEqual(project.log[0].date, date(2026, 10, 1))
        self.assertIn("Horkheimer", project.log[0].note or "")

    def test_missing_deadline(self) -> None:
        text = "# T\n\nStatus: active\nStage: 材料\nDeadline:\n"
        project = parser.parse_project(text, "t")
        self.assertIsNone(project.deadline)
        self.assertEqual(project.stage, "材料")

    def test_chinese_title_and_stage(self) -> None:
        text = "# 欧洲中世纪博物学\n\nStatus: active\nStage: 初稿\n"
        project = parser.parse_project(text, "medieval")
        self.assertEqual(project.title, "欧洲中世纪博物学")
        self.assertEqual(project.stage, "初稿")

    def test_empty_current_and_next(self) -> None:
        text = "# T\n\nStatus: active\n\n## Current\n\n## Next\n\n## Log\n"
        project = parser.parse_project(text, "t")
        self.assertEqual(project.current, "")
        self.assertEqual(project.next, "")
        self.assertEqual(project.log, [])

    def test_default_status_when_missing(self) -> None:
        project = parser.parse_project("# T\n", "t")
        self.assertEqual(project.status, "active")

    def test_unknown_section_is_ignored_but_not_dropped(self) -> None:
        text = PROJECT + "\n## 自定义\n\n用户自己加的东西\n"
        project = parser.parse_project(text, "x")
        self.assertEqual(project.title, "Frankfurt School and Early HPS")


class ConservativeProjectWriteTests(unittest.TestCase):
    def test_set_status_changes_only_status_line(self) -> None:
        out = parser.set_project_status(PROJECT, "paused")
        self.assertIn("Status: paused", out)
        self.assertEqual(out.count("Status:"), 1)
        # 其余内容逐字保留
        self.assertIn("Stage: 重写", out)
        self.assertIn("重写第二节。", out)
        self.assertIn("- 2026-09-27 — 查阅 Grossmann 与 Horkheimer 材料。", out)

    def test_unchanged_value_returns_identical_text(self) -> None:
        self.assertEqual(parser.set_project_status(PROJECT, "active"), PROJECT)

    def test_unknown_section_preserved(self) -> None:
        text = PROJECT + "\n## 自定义\n\n用户自己加的东西\n"
        out = parser.set_project_status(text, "done")
        self.assertIn("## 自定义", out)
        self.assertIn("用户自己加的东西", out)

    def test_set_stage_to_empty(self) -> None:
        out = parser.set_project_stage(PROJECT, None)
        self.assertIn("Stage:", out)
        self.assertIsNone(parser.parse_project(out, "x").stage)

    def test_set_deadline(self) -> None:
        out = parser.set_project_deadline(PROJECT, date(2027, 1, 15))
        self.assertIn("Deadline: 2027-01-15", out)
        self.assertEqual(parser.parse_project(out, "x").deadline, date(2027, 1, 15))

    def test_append_log_with_note(self) -> None:
        out = parser.append_project_log(PROJECT, date(2026, 10, 2), "继续第二节")
        self.assertIn("- 2026-10-02 — 继续第二节", out)
        self.assertEqual(len(parser.parse_project(out, "x").log), 4)

    def test_append_log_without_note(self) -> None:
        out = parser.append_project_log(PROJECT, date(2026, 10, 2))
        self.assertIn("- 2026-10-02\n", out)
        entries = parser.parse_project(out, "x").log
        self.assertEqual(entries[0].date, date(2026, 10, 2))
        self.assertIsNone(entries[0].note)

    def test_set_current_keeps_next(self) -> None:
        out = parser.set_project_current(PROJECT, "改写导论。")
        project = parser.parse_project(out, "x")
        self.assertEqual(project.current, "改写导论。")
        self.assertEqual(project.next, "处理 Horkheimer 与 HPS 之间的关系。")

    def test_render_new_project_roundtrip(self) -> None:
        text = parser.render_new_project(
            "medieval-natural-history", "欧洲中世纪博物学", stage="初稿"
        )
        project = parser.parse_project(text, "medieval-natural-history")
        self.assertEqual(project.title, "欧洲中世纪博物学")
        self.assertEqual(project.status, "active")
        self.assertEqual(project.stage, "初稿")
        self.assertIsNone(project.deadline)
        self.assertEqual(project.current, "")
        self.assertEqual(project.next, "")
        self.assertEqual(project.log, [])


class ParseDayTests(unittest.TestCase):
    def test_parse_full_day(self) -> None:
        record = parser.parse_day(DAY, date(2026, 10, 1))
        self.assertEqual(record.focus, "frankfurt-hps")
        self.assertTrue(record.routines["reading"])
        self.assertTrue(record.routines["writing"])
        self.assertFalse(record.routines["email"])
        self.assertFalse(record.routines["admin"])
        self.assertEqual(record.projects, {"frankfurt-hps"})
        self.assertEqual(record.notes, ["Frankfurt HPS：第二节继续推进。"])

    def test_render_new_day_roundtrip(self) -> None:
        text = parser.render_new_day(date(2026, 10, 1))
        record = parser.parse_day(text, date(2026, 10, 1))
        self.assertIsNone(record.focus)
        self.assertEqual(set(record.routines), set(ROUTINES))
        self.assertFalse(any(record.routines.values()))
        self.assertEqual(record.projects, set())
        self.assertEqual(record.notes, [])

    def test_set_focus(self) -> None:
        out = parser.set_day_focus(DAY, "medieval-natural-history")
        self.assertEqual(
            parser.parse_day(out, date(2026, 10, 1)).focus,
            "medieval-natural-history",
        )

    def test_clear_focus(self) -> None:
        out = parser.set_day_focus(DAY, None)
        self.assertIn("Focus:", out)
        self.assertIsNone(parser.parse_day(out, date(2026, 10, 1)).focus)

    def test_routine_done_then_undo(self) -> None:
        done = parser.set_routine(DAY, "admin", True)
        self.assertTrue(parser.parse_day(done, date(2026, 10, 1)).routines["admin"])
        undone = parser.set_routine(done, "reading", False)
        self.assertFalse(
            parser.parse_day(undone, date(2026, 10, 1)).routines["reading"]
        )

    def test_routine_name_case_insensitive(self) -> None:
        out = parser.set_routine(DAY, "EMAIL", True)
        self.assertTrue(parser.parse_day(out, date(2026, 10, 1)).routines["email"])

    def test_add_day_project_idempotent(self) -> None:
        out = parser.add_day_project(DAY, "frankfurt-hps")
        self.assertEqual(out, DAY)  # 已存在，无需改动
        out2 = parser.add_day_project(out, "medieval-natural-history")
        self.assertEqual(
            parser.parse_day(out2, date(2026, 10, 1)).projects,
            {"frankfurt-hps", "medieval-natural-history"},
        )

    def test_append_day_note(self) -> None:
        out = parser.append_day_note(DAY, "明天继续")
        notes = parser.parse_day(out, date(2026, 10, 1)).notes
        self.assertIn("明天继续", notes)


if __name__ == "__main__":
    unittest.main()
