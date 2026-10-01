"""回顾统计。

事实来源：``days/`` 每日记录为主，项目 ``## Log`` 为辅助。两者按"不同自然日"去重后合并。

核心指标是**连续性**，不是完成率：

- 最近一次接触；
- 最近 7 个自然日内的接触天数；
- 最近 30 个自然日内的接触天数。

不产生评分、等级、streak 等指标。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import parser, storage
from .models import ROUTINES, DayRecord, ProjectLogEntry

#: 超过该天数未推进即视为"久未推进"（仅作视觉提醒）。
STALE_DAYS = 7


# --------------------------------------------------------------------------- #
# 结果类型
# --------------------------------------------------------------------------- #
@dataclass
class ProjectReview:
    project_id: str
    title: str
    status: str
    last_touched: date | None
    days_since: int | None
    days_7: int
    days_30: int


@dataclass
class ReviewReport:
    projects: list[ProjectReview] = field(default_factory=list)
    active_count: int = 0
    touched_this_week: int = 0
    stale_over_7: int = 0


@dataclass
class WeekSummary:
    year: int
    week: int
    monday: date
    sunday: date
    routine_days: dict[str, list[bool]] = field(default_factory=dict)
    project_days: dict[str, list[bool]] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 内部：读取与索引
# --------------------------------------------------------------------------- #
def _parse_day_stem(stem: str) -> date | None:
    try:
        return date.fromisoformat(stem)
    except ValueError:
        return None


def _all_day_records(data_dir) -> dict[date, DayRecord]:
    records: dict[date, DayRecord] = {}
    directory = storage.days_dir(data_dir)
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*.md")):
        day = _parse_day_stem(path.stem)
        if day is None:
            continue
        text = storage.read_text_safe(path)
        if text is None:
            continue
        records[day] = parser.parse_day(text, day)
    return records


def _day_index(records: dict[date, DayRecord]) -> dict[str, set[date]]:
    """项目 ID → 在每日记录中被标记的日期集合。"""
    index: dict[str, set[date]] = {}
    for day, record in records.items():
        for project_id in record.projects:
            index.setdefault(project_id, set()).add(day)
    return index


def _log_dates(data_dir, project_id: str) -> set[date]:
    text = storage.read_text_safe(storage.project_path(data_dir, project_id))
    if not text:
        return set()
    project = parser.parse_project(text, project_id)
    return {entry.date for entry in project.log if entry.date is not None}


def contact_dates(data_dir, project_id: str) -> set[date]:
    """项目被接触过的所有日期（每日记录 ∪ 项目 Log，去重）。"""
    dates = set()
    for day, record in _all_day_records(data_dir).items():
        if project_id in record.projects:
            dates.add(day)
    dates |= _log_dates(data_dir, project_id)
    return dates


# --------------------------------------------------------------------------- #
# 单项目指标
# --------------------------------------------------------------------------- #
def last_touched_date(data_dir, project_id: str) -> date | None:
    dates = contact_dates(data_dir, project_id)
    return max(dates) if dates else None


def last_touched_map(
    data_dir, project_ids: list[str] | None = None
) -> dict[str, date | None]:
    """一次性算出多个项目的最近推进日期。

    只读取一遍 ``days/``，避免逐个项目重复扫描（首页/项目列表用）。
    """
    records = _all_day_records(data_dir)
    index = _day_index(records)
    if project_ids is None:
        project_ids = storage.list_project_ids(data_dir)
    result: dict[str, date | None] = {}
    for project_id in project_ids:
        dates = set(index.get(project_id, set())) | _log_dates(data_dir, project_id)
        result[project_id] = max(dates) if dates else None
    return result


def days_since_touched(
    data_dir, project_id: str, *, today: date | None = None
) -> int | None:
    today = today or date.today()
    last = last_touched_date(data_dir, project_id)
    return None if last is None else (today - last).days


def _count_in_window(dates: set[date], today: date, days: int) -> int:
    start = today - timedelta(days=days - 1)
    return sum(1 for d in dates if start <= d <= today)


def contact_count(
    data_dir, project_id: str, *, days: int, today: date | None = None
) -> int:
    """最近 ``days`` 个自然日内被接触的**不同日期**数量。"""
    today = today or date.today()
    return _count_in_window(contact_dates(data_dir, project_id), today, days)


def project_history(
    data_dir, project_id: str, *, limit: int | None = None, archived: bool = False
) -> list[ProjectLogEntry]:
    """项目历史记录，按日期倒序（无日期的条目排在最后）。"""
    path = (
        storage.archive_path(data_dir, project_id)
        if archived
        else storage.project_path(data_dir, project_id)
    )
    text = storage.read_text_if_exists(path)
    if not text:
        return []
    entries = [e for e in parser.parse_project(text, project_id).log if e.date]
    entries.sort(key=lambda e: e.date, reverse=True)
    return entries[:limit] if limit is not None else entries


def month_touched_days(data_dir, project_id: str, year: int, month: int) -> set[int]:
    """某年某月中项目被接触的日期。"""
    return {
        d.day
        for d in contact_dates(data_dir, project_id)
        if d.year == year and d.month == month
    }


# --------------------------------------------------------------------------- #
# 全部项目回顾
# --------------------------------------------------------------------------- #
def review_all(
    data_dir, *, today: date | None = None, status: str | None = "active"
) -> ReviewReport:
    today = today or date.today()
    records = _all_day_records(data_dir)
    day_index = _day_index(records)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    reviews: list[ProjectReview] = []
    for project_id in storage.list_project_ids(data_dir):
        text = storage.read_text_safe(storage.project_path(data_dir, project_id))
        if text is None:
            continue
        project = parser.parse_project(text, project_id)
        if status is not None and project.status != status:
            continue
        dates = set(day_index.get(project_id, set())) | _log_dates(
            data_dir, project_id
        )
        last = max(dates) if dates else None
        reviews.append(
            ProjectReview(
                project_id=project_id,
                title=project.title,
                status=project.status,
                last_touched=last,
                days_since=None if last is None else (today - last).days,
                days_7=_count_in_window(dates, today, 7),
                days_30=_count_in_window(dates, today, 30),
            )
        )

    # 最久未推进者排在最前（从未接触视为最久）。
    reviews.sort(
        key=lambda r: r.days_since if r.days_since is not None else 10**9,
        reverse=True,
    )

    report = ReviewReport(projects=reviews)
    report.active_count = sum(1 for r in reviews if r.status == "active")
    report.touched_this_week = sum(
        1
        for r in reviews
        if r.last_touched is not None and week_start <= r.last_touched <= week_end
    )
    report.stale_over_7 = sum(
        1 for r in reviews if r.days_since is None or r.days_since > STALE_DAYS
    )
    return report


# --------------------------------------------------------------------------- #
# 周回顾
# --------------------------------------------------------------------------- #
def week_summary(data_dir, *, day: date | None = None) -> WeekSummary:
    day = day or date.today()
    monday = day - timedelta(days=day.weekday())
    iso = monday.isocalendar()
    records = _all_day_records(data_dir)

    # 只统计当前仍存在的项目（已删除的 id 不再出现在周回顾里；归档的仍保留历史）。
    known = set(storage.list_project_ids(data_dir))
    archive = storage.archive_dir(data_dir)
    if archive.is_dir():
        known |= {path.stem for path in archive.glob("*.md") if path.is_file()}

    routine_days: dict[str, list[bool]] = {name: [] for name in ROUTINES}
    project_days: dict[str, list[bool]] = {}

    for i in range(7):
        current = monday + timedelta(days=i)
        record = records.get(current)
        for name in ROUTINES:
            routine_days[name].append(bool(record and record.routines.get(name)))
        if record:
            for project_id in record.projects:
                if project_id not in known:
                    continue
                project_days.setdefault(project_id, [False] * 7)[i] = True

    return WeekSummary(
        year=iso.year,
        week=iso.week,
        monday=monday,
        sunday=monday + timedelta(days=6),
        routine_days=routine_days,
        project_days=project_days,
    )
