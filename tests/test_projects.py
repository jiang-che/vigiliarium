"""项目业务操作测试。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from vigi import days, parser, projects, storage

DAY = date(2026, 10, 1)


class ProjectTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        storage.ensure_data_dirs(self.data_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class CreateProjectTests(ProjectTestCase):
    def test_create_and_load(self) -> None:
        project = projects.create_project(
            self.data_dir, "medieval-natural-history", "欧洲中世纪博物学", stage="初稿"
        )
        self.assertEqual(project.status, "active")
        self.assertTrue(
            storage.project_path(self.data_dir, "medieval-natural-history").is_file()
        )
        loaded = projects.load_project(self.data_dir, "medieval-natural-history")
        self.assertEqual(loaded.title, "欧洲中世纪博物学")
        self.assertEqual(loaded.stage, "初稿")

    def test_invalid_id_rejected(self) -> None:
        for bad in ("../evil", "a/b", "", ".hidden", "a..b"):
            with self.assertRaises(ValueError):
                projects.create_project(self.data_dir, bad, "T")

    def test_duplicate_rejected(self) -> None:
        projects.create_project(self.data_dir, "dup", "T")
        with self.assertRaises(FileExistsError):
            projects.create_project(self.data_dir, "dup", "T2")

    def test_invalid_status_rejected(self) -> None:
        with self.assertRaises(ValueError):
            projects.create_project(self.data_dir, "x", "T", status="bogus")


class UpdateProjectTests(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        projects.create_project(
            self.data_dir, "frankfurt-hps", "Frankfurt School and Early HPS", stage="重写"
        )

    def test_set_status(self) -> None:
        project = projects.set_status(self.data_dir, "frankfurt-hps", "paused")
        self.assertEqual(project.status, "paused")

    def test_set_status_invalid(self) -> None:
        with self.assertRaises(ValueError):
            projects.set_status(self.data_dir, "frankfurt-hps", "bogus")

    def test_set_current_and_next(self) -> None:
        projects.set_current(self.data_dir, "frankfurt-hps", "改写导论。")
        project = projects.set_next(self.data_dir, "frankfurt-hps", "接 Neurath。")
        self.assertEqual(project.current, "改写导论。")
        self.assertEqual(project.next, "接 Neurath。")

    def test_set_deadline(self) -> None:
        project = projects.set_deadline(
            self.data_dir, "frankfurt-hps", date(2026, 11, 30)
        )
        self.assertEqual(project.deadline, date(2026, 11, 30))

    def test_missing_project_raises(self) -> None:
        with self.assertRaises(projects.ProjectNotFound):
            projects.load_project(self.data_dir, "nope")

    def test_list_filter_by_status(self) -> None:
        projects.create_project(self.data_dir, "idea-1", "想法一", status="idea")
        active = projects.list_projects(self.data_dir, status="active")
        self.assertEqual([p.project_id for p in active], ["frankfurt-hps"])
        self.assertEqual(len(projects.list_projects(self.data_dir)), 2)


class TouchTests(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        projects.create_project(self.data_dir, "frankfurt-hps", "Frankfurt HPS")

    def test_first_touch_marks_day_and_log(self) -> None:
        project = projects.touch(self.data_dir, "frankfurt-hps", day=DAY)
        self.assertEqual(len(project.log), 1)
        self.assertEqual(project.log[0].date, DAY)
        self.assertIsNone(project.log[0].note)
        self.assertEqual(days.touched_projects(self.data_dir, DAY), {"frankfurt-hps"})

    def test_second_bare_touch_does_not_duplicate(self) -> None:
        projects.touch(self.data_dir, "frankfurt-hps", day=DAY)
        project = projects.touch(self.data_dir, "frankfurt-hps", day=DAY)
        self.assertEqual(len(project.log), 1)

    def test_note_touch_appends(self) -> None:
        projects.touch(self.data_dir, "frankfurt-hps", day=DAY)
        project = projects.touch(
            self.data_dir, "frankfurt-hps", day=DAY, note="第二节基本改完"
        )
        self.assertEqual(len(project.log), 2)
        notes = [entry.note for entry in project.log if entry.date == DAY]
        self.assertIn("第二节基本改完", notes)
        # 再次无备注不新增
        project = projects.touch(self.data_dir, "frankfurt-hps", day=DAY)
        self.assertEqual(len(project.log), 2)

    def test_touch_unknown_project(self) -> None:
        with self.assertRaises(projects.ProjectNotFound):
            projects.touch(self.data_dir, "nope", day=DAY)

    def test_day_file_created_with_checkbox(self) -> None:
        projects.touch(self.data_dir, "frankfurt-hps", day=DAY)
        text = storage.read_text(storage.day_path(self.data_dir, DAY))
        self.assertIn("- [x] frankfurt-hps", text)
        self.assertIn("# 2026-10-01", text)


class FocusTests(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        projects.create_project(self.data_dir, "frankfurt-hps", "Frankfurt HPS")
        projects.create_project(self.data_dir, "medieval-nh", "Medieval NH")

    def test_set_focus_overwrites(self) -> None:
        projects.set_focus(self.data_dir, "frankfurt-hps", day=DAY)
        self.assertEqual(days.load_day(self.data_dir, DAY).focus, "frankfurt-hps")
        projects.set_focus(self.data_dir, "medieval-nh", day=DAY)
        self.assertEqual(days.load_day(self.data_dir, DAY).focus, "medieval-nh")

    def test_clear_focus(self) -> None:
        projects.set_focus(self.data_dir, "frankfurt-hps", day=DAY)
        projects.clear_focus(self.data_dir, day=DAY)
        self.assertIsNone(days.load_day(self.data_dir, DAY).focus)

    def test_focus_unknown_project(self) -> None:
        with self.assertRaises(projects.ProjectNotFound):
            projects.set_focus(self.data_dir, "nope", day=DAY)


class ArchiveDeleteTests(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        projects.create_project(self.data_dir, "a", "A")

    def test_archive_moves_file(self) -> None:
        target = projects.archive_project(self.data_dir, "a")
        self.assertTrue(target.is_file())
        self.assertFalse(storage.project_path(self.data_dir, "a").is_file())
        self.assertEqual(storage.list_project_ids(self.data_dir), [])

    def test_archive_existing_target_raises(self) -> None:
        projects.archive_project(self.data_dir, "a")
        projects.create_project(self.data_dir, "a", "A")
        with self.assertRaises(FileExistsError):
            projects.archive_project(self.data_dir, "a")

    def test_archive_missing(self) -> None:
        with self.assertRaises(projects.ProjectNotFound):
            projects.archive_project(self.data_dir, "nope")

    def test_delete_removes_file(self) -> None:
        projects.delete_project(self.data_dir, "a")
        self.assertFalse(storage.project_path(self.data_dir, "a").is_file())

    def test_delete_missing(self) -> None:
        with self.assertRaises(projects.ProjectNotFound):
            projects.delete_project(self.data_dir, "nope")

    def test_unarchive_moves_back(self) -> None:
        projects.archive_project(self.data_dir, "a")
        target = projects.unarchive_project(self.data_dir, "a")
        self.assertTrue(target.is_file())
        self.assertFalse(storage.archive_path(self.data_dir, "a").is_file())

    def test_unarchive_missing(self) -> None:
        with self.assertRaises(projects.ProjectNotFound):
            projects.unarchive_project(self.data_dir, "nope")

    def test_unarchive_existing_target_raises(self) -> None:
        projects.archive_project(self.data_dir, "a")
        projects.create_project(self.data_dir, "a", "A")
        with self.assertRaises(FileExistsError):
            projects.unarchive_project(self.data_dir, "a")

    def test_forget_project_clears_today_focus(self) -> None:
        projects.set_focus(self.data_dir, "a", day=DAY)
        projects.forget_project(self.data_dir, "a", day=DAY)
        self.assertIsNone(days.load_day(self.data_dir, DAY).focus)

    def test_forget_project_keeps_other_focus(self) -> None:
        projects.create_project(self.data_dir, "b", "B")
        projects.set_focus(self.data_dir, "b", day=DAY)
        projects.forget_project(self.data_dir, "a", day=DAY)
        self.assertEqual(days.load_day(self.data_dir, DAY).focus, "b")


class ArchivedQueryTests(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        projects.create_project(self.data_dir, "a", "A")
        projects.create_project(self.data_dir, "b", "B")
        projects.archive_project(self.data_dir, "b")

    def test_list_archived(self) -> None:
        archived = projects.list_archived_projects(self.data_dir)
        self.assertEqual([p.project_id for p in archived], ["b"])
        self.assertEqual(archived[0].title, "B")

    def test_load_archived(self) -> None:
        project = projects.load_archived_project(self.data_dir, "b")
        self.assertEqual(project.title, "B")

    def test_load_archived_missing(self) -> None:
        with self.assertRaises(projects.ProjectNotFound):
            projects.load_archived_project(self.data_dir, "nope")

    def test_delete_archived(self) -> None:
        projects.delete_archived_project(self.data_dir, "b")
        self.assertFalse(storage.archive_path(self.data_dir, "b").is_file())


if __name__ == "__main__":
    unittest.main()
