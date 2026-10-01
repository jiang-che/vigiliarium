"""回顾统计测试。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from vigi import days, projects, review, storage

TODAY = date(2026, 10, 15)


class ReviewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        storage.ensure_data_dirs(self.data_dir)
        projects.create_project(self.data_dir, "frankfurt-hps", "Frankfurt HPS")
        projects.create_project(self.data_dir, "medieval-nh", "Medieval NH")
        projects.create_project(self.data_dir, "never-touched", "Never Touched")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def touch(self, project_id: str, day: date, note: str | None = None) -> None:
        projects.touch(self.data_dir, project_id, day=day, note=note)


class ContactMetricTests(ReviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        for day in (
            date(2026, 10, 15),
            date(2026, 10, 9),
            date(2026, 10, 8),
            date(2026, 9, 20),
            date(2026, 9, 1),
        ):
            self.touch("frankfurt-hps", day)
        self.touch("medieval-nh", date(2026, 10, 1))

    def test_last_touched_and_days_since(self) -> None:
        self.assertEqual(
            review.last_touched_date(self.data_dir, "frankfurt-hps"),
            date(2026, 10, 15),
        )
        self.assertEqual(
            review.days_since_touched(
                self.data_dir, "frankfurt-hps", today=TODAY
            ),
            0,
        )
        self.assertEqual(
            review.days_since_touched(self.data_dir, "medieval-nh", today=TODAY),
            14,
        )

    def test_never_touched(self) -> None:
        self.assertIsNone(review.last_touched_date(self.data_dir, "never-touched"))
        self.assertIsNone(
            review.days_since_touched(
                self.data_dir, "never-touched", today=TODAY
            )
        )
        self.assertEqual(
            review.contact_count(
                self.data_dir, "never-touched", days=30, today=TODAY
            ),
            0,
        )

    def test_contact_count_7_day_window(self) -> None:
        # 窗口 = 10-09 .. 10-15，故 10-08 不计
        self.assertEqual(
            review.contact_count(
                self.data_dir, "frankfurt-hps", days=7, today=TODAY
            ),
            2,
        )

    def test_contact_count_30_day_window(self) -> None:
        # 窗口 = 09-16 .. 10-15，故 09-01 不计
        self.assertEqual(
            review.contact_count(
                self.data_dir, "frankfurt-hps", days=30, today=TODAY
            ),
            4,
        )

    def test_same_day_counts_once(self) -> None:
        self.touch("medieval-nh", date(2026, 10, 14))
        self.touch("medieval-nh", date(2026, 10, 14), note="又推进了一次")
        # 7 天窗口 10-09..10-15：只有 10-14 命中，且同一天多次只算 1
        self.assertEqual(
            review.contact_count(self.data_dir, "medieval-nh", days=7, today=TODAY), 1
        )
        # 30 天窗口包含 10-01 与 10-14，共 2 个不同日期
        self.assertEqual(
            review.contact_count(self.data_dir, "medieval-nh", days=30, today=TODAY), 2
        )


class ProjectHistoryTests(ReviewTestCase):
    def test_history_sorted_desc(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 1), note="a")
        self.touch("frankfurt-hps", date(2026, 10, 10), note="b")
        history = review.project_history(self.data_dir, "frankfurt-hps")
        self.assertEqual([e.date for e in history], [date(2026, 10, 10), date(2026, 10, 1)])

    def test_history_limit(self) -> None:
        for day in (date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)):
            self.touch("frankfurt-hps", day)
        self.assertEqual(
            len(review.project_history(self.data_dir, "frankfurt-hps", limit=2)), 2
        )

    def test_month_touched_days(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 5))
        self.touch("frankfurt-hps", date(2026, 10, 20))
        self.touch("frankfurt-hps", date(2026, 9, 30))
        self.assertEqual(
            review.month_touched_days(self.data_dir, "frankfurt-hps", 2026, 10),
            {5, 20},
        )


class ReviewAllTests(ReviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.touch("frankfurt-hps", date(2026, 10, 15))
        self.touch("frankfurt-hps", date(2026, 10, 9))
        self.touch("medieval-nh", date(2026, 10, 1))

    def test_report_counts(self) -> None:
        report = review.review_all(self.data_dir, today=TODAY)
        self.assertEqual(report.active_count, 3)
        self.assertEqual(report.touched_this_week, 1)  # 仅 frankfurt 在 10-12..10-18
        self.assertEqual(report.stale_over_7, 2)  # medieval(14) 与 never

    def test_sorted_most_stale_first(self) -> None:
        report = review.review_all(self.data_dir, today=TODAY)
        self.assertEqual(report.projects[0].project_id, "never-touched")
        self.assertEqual(report.projects[-1].project_id, "frankfurt-hps")
        frankfurt = next(
            p for p in report.projects if p.project_id == "frankfurt-hps"
        )
        self.assertEqual((frankfurt.days_7, frankfurt.days_30), (2, 2))

    def test_status_filter(self) -> None:
        projects.set_status(self.data_dir, "medieval-nh", "paused")
        report = review.review_all(self.data_dir, today=TODAY, status="active")
        self.assertEqual(
            [p.project_id for p in report.projects if p.project_id == "medieval-nh"],
            [],
        )


class WeekSummaryTests(ReviewTestCase):
    def test_week_boundaries_cross_month(self) -> None:
        summary = review.week_summary(self.data_dir, day=date(2026, 9, 30))
        self.assertEqual(summary.monday, date(2026, 9, 28))
        self.assertEqual(summary.sunday, date(2026, 10, 4))

    def test_week_boundaries_cross_year(self) -> None:
        summary = review.week_summary(self.data_dir, day=date(2026, 1, 1))
        self.assertEqual((summary.year, summary.week), (2026, 1))
        self.assertEqual(summary.monday, date(2025, 12, 29))
        self.assertEqual(summary.sunday, date(2026, 1, 4))

    def test_iso_week_matches_stdlib(self) -> None:
        summary = review.week_summary(self.data_dir, day=TODAY)
        iso = TODAY.isocalendar()
        self.assertEqual((summary.year, summary.week), (iso.year, iso.week))

    def test_routine_and_project_days(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 13))
        self.touch("frankfurt-hps", date(2026, 10, 15))
        days.done(self.data_dir, "reading", day=date(2026, 10, 13))
        summary = review.week_summary(self.data_dir, day=TODAY)
        # monday = 2026-10-12 → 索引 1 = 10-13，索引 3 = 10-15
        self.assertEqual(summary.routine_days["reading"][1], True)
        self.assertEqual(summary.routine_days["writing"][1], False)
        self.assertEqual(summary.project_days["frankfurt-hps"][1], True)
        self.assertEqual(summary.project_days["frankfurt-hps"][3], True)


class RobustnessTests(ReviewTestCase):
    def test_unreadable_project_skipped(self) -> None:
        storage.project_path(self.data_dir, "bad").write_bytes(b"\xff\xfe\x00")
        report = review.review_all(self.data_dir, status=None)
        self.assertNotIn("bad", [item.project_id for item in report.projects])

    def test_unreadable_day_skipped(self) -> None:
        (storage.days_dir(self.data_dir) / "2026-10-15.md").write_bytes(b"\xff\xfe")
        summary = review.week_summary(self.data_dir, day=TODAY)
        self.assertFalse(summary.routine_days["reading"][3])


class WeekSummaryFilterTests(ReviewTestCase):
    def test_deleted_project_excluded(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 13))
        projects.delete_project(self.data_dir, "frankfurt-hps")
        summary = review.week_summary(self.data_dir, day=TODAY)
        self.assertNotIn("frankfurt-hps", summary.project_days)

    def test_archived_project_history_kept(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 13))
        projects.archive_project(self.data_dir, "frankfurt-hps")
        summary = review.week_summary(self.data_dir, day=TODAY)
        self.assertIn("frankfurt-hps", summary.project_days)

    def test_project_history_from_archive(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 15), note="x")
        projects.archive_project(self.data_dir, "frankfurt-hps")
        history = review.project_history(
            self.data_dir, "frankfurt-hps", archived=True
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].note, "x")


class LastTouchedMapTests(ReviewTestCase):
    def test_map_by_project(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 15))
        self.touch("medieval-nh", date(2026, 10, 1))
        result = review.last_touched_map(self.data_dir)
        self.assertEqual(result["frankfurt-hps"], date(2026, 10, 15))
        self.assertEqual(result["medieval-nh"], date(2026, 10, 1))
        self.assertIsNone(result["never-touched"])

    def test_subset(self) -> None:
        self.touch("frankfurt-hps", date(2026, 10, 15))
        result = review.last_touched_map(self.data_dir, ["frankfurt-hps"])
        self.assertEqual(set(result), {"frankfurt-hps"})


if __name__ == "__main__":
    unittest.main()
