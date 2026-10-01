"""每日记录业务操作。

负责今日文件的自动创建、例行事项打卡/取消、备注与"当天接触过的项目"查询。
"""

from __future__ import annotations

from datetime import date as Date

from . import parser, storage
from .models import ROUTINES, DayRecord


class UnknownRoutine(ValueError):
    """例行事项名称不在固定四项之内。"""


def _validate_routine(name: str) -> str:
    key = name.casefold()
    if key not in ROUTINES:
        raise UnknownRoutine(name)
    return key


def load_day(data_dir, day: Date, *, create: bool = True) -> DayRecord:
    """读取某天的记录；不存在且 ``create=True`` 时自动创建文件。

    文件存在但无法按 UTF-8 解析时，视为空记录，且**不覆盖**以免丢数据。
    """
    path = storage.day_path(data_dir, day)
    exists = path.exists()
    text: str | None = None
    if exists:
        try:
            text = storage.read_text(path)
        except UnicodeDecodeError:
            text = None
    if text is None:
        if exists:
            return parser.parse_day(parser.render_new_day(day), day)
        text = parser.render_new_day(day)
        if create:
            storage.write_text(path, text)
    return parser.parse_day(text, day)


def ensure_day(data_dir, day: Date) -> DayRecord:
    """确保当天文件存在并返回其记录。"""
    return load_day(data_dir, day, create=True)


def set_routine(
    data_dir, day: Date, name: str, done: bool, *, create: bool = True
) -> DayRecord:
    """打卡 / 取消某个例行事项。``name`` 大小写不敏感。"""
    key = _validate_routine(name)
    path = storage.day_path(data_dir, day)
    text = storage.read_text_if_exists(path)
    if text is None:
        text = parser.render_new_day(day)
        if not create:
            return parser.parse_day(parser.set_routine(text, key, done), day)
    new_text = parser.set_routine(text, key, done)
    storage.write_text_if_changed(path, new_text)
    return parser.parse_day(new_text, day)


def done(data_dir, name: str, *, day: Date | None = None) -> DayRecord:
    return set_routine(data_dir, day or Date.today(), name, True)


def undo(data_dir, name: str, *, day: Date | None = None) -> DayRecord:
    return set_routine(data_dir, day or Date.today(), name, False)


def append_note(data_dir, day: Date, note: str, *, create: bool = True) -> DayRecord:
    path = storage.day_path(data_dir, day)
    text = storage.read_text_if_exists(path)
    if text is None:
        text = parser.render_new_day(day)
        if not create:
            return parser.parse_day(parser.append_day_note(text, note), day)
    new_text = parser.append_day_note(text, note)
    storage.write_text_if_changed(path, new_text)
    return parser.parse_day(new_text, day)


def touched_projects(data_dir, day: Date) -> set[str]:
    """某天接触过的项目集合；文件不存在时返回空集（不创建文件）。"""
    text = storage.read_text_if_exists(storage.day_path(data_dir, day))
    if text is None:
        return set()
    return parser.parse_day(text, day).projects
