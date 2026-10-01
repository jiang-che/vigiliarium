"""每日记录业务操作测试。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from vigi import days, storage

DAY = date(2026, 10, 1)


class DayTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        storage.ensure_data_dirs(self.data_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class LoadDayTests(DayTestCase):
    def test_auto_creates_file(self) -> None:
        path = storage.day_path(self.data_dir, DAY)
        self.assertFalse(path.exists())
        record = days.load_day(self.data_dir, DAY)
        self.assertTrue(path.exists())
        self.assertEqual(record.date, DAY)
        self.assertFalse(any(record.routines.values()))

    def test_load_without_create(self) -> None:
        day = date(2026, 10, 2)
        days.load_day(self.data_dir, day, create=False)
        self.assertFalse(storage.day_path(self.data_dir, day).exists())


class RoutineTests(DayTestCase):
    def test_done_then_undo(self) -> None:
        record = days.done(self.data_dir, "reading", day=DAY)
        self.assertTrue(record.routines["reading"])
        record = days.undo(self.data_dir, "reading", day=DAY)
        self.assertFalse(record.routines["reading"])

    def test_all_four_routines(self) -> None:
        for name in ("reading", "writing", "email", "admin"):
            days.done(self.data_dir, name, day=DAY)
        record = days.load_day(self.data_dir, DAY)
        self.assertTrue(all(record.routines[name] for name in record.routines))

    def test_unknown_routine_rejected(self) -> None:
        with self.assertRaises(days.UnknownRoutine):
            days.done(self.data_dir, "cooking", day=DAY)

    def test_written_as_english_names(self) -> None:
        days.done(self.data_dir, "reading", day=DAY)
        text = storage.read_text(storage.day_path(self.data_dir, DAY))
        self.assertIn("- [x] Reading", text)
        self.assertIn("- [ ] Admin", text)


class CorruptDayFileTests(DayTestCase):
    def test_corrupt_day_file_not_overwritten(self) -> None:
        path = storage.day_path(self.data_dir, DAY)
        path.write_bytes(b"\xff\xfe\x00")
        record = days.load_day(self.data_dir, DAY)
        self.assertEqual(record.date, DAY)
        self.assertFalse(any(record.routines.values()))
        self.assertEqual(path.read_bytes(), b"\xff\xfe\x00")


class NoCreateFlagTests(DayTestCase):
    def test_set_routine_without_create(self) -> None:
        record = days.set_routine(self.data_dir, DAY, "reading", True, create=False)
        self.assertTrue(record.routines["reading"])
        self.assertFalse(storage.day_path(self.data_dir, DAY).exists())

    def test_append_note_without_create(self) -> None:
        record = days.append_note(self.data_dir, DAY, "x", create=False)
        self.assertIn("x", record.notes)
        self.assertFalse(storage.day_path(self.data_dir, DAY).exists())


class NoteAndQueryTests(DayTestCase):
    def test_append_note(self) -> None:
        record = days.append_note(self.data_dir, DAY, "今天状态一般")
        self.assertIn("今天状态一般", record.notes)

    def test_touched_projects_empty_when_no_file(self) -> None:
        self.assertEqual(days.touched_projects(self.data_dir, DAY), set())
        # 不应创建文件
        self.assertFalse(storage.day_path(self.data_dir, DAY).exists())


if __name__ == "__main__":
    unittest.main()
