"""项目相关业务操作。

本层只做编排：读文件 → 调用 ``parser`` 的保守写回 → 原子落盘。
不直接拼接 Markdown 文本。
"""

from __future__ import annotations

import os
import re
from datetime import date as Date
from pathlib import Path
from typing import Callable

from . import parser, storage
from .models import PROJECT_STATUSES, Project

#: 允许的项目 ID：字母数字开头，其后可含字母数字、点、下划线、连字符。
#: 明确的路径穿越风险（``/``、``..``、前导点）一律拒绝。
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ProjectNotFound(LookupError):
    """引用了不存在的项目。"""

    def __init__(self, project_id: str) -> None:
        super().__init__(project_id)
        self.project_id = project_id


def is_valid_project_id(project_id: str) -> bool:
    return bool(_ID_RE.match(project_id)) and ".." not in project_id


def project_exists(data_dir, project_id: str) -> bool:
    return storage.project_path(data_dir, project_id).is_file()


def load_project(data_dir, project_id: str) -> Project:
    path = storage.project_path(data_dir, project_id)
    if not path.is_file():
        raise ProjectNotFound(project_id)
    text = storage.read_text_safe(path)
    if text is None:
        raise ProjectNotFound(project_id)
    return parser.parse_project(text, project_id)


def load_archived_project(data_dir, project_id: str) -> Project:
    path = storage.archive_path(data_dir, project_id)
    if not path.is_file():
        raise ProjectNotFound(project_id)
    text = storage.read_text_safe(path)
    if text is None:
        raise ProjectNotFound(project_id)
    return parser.parse_project(text, project_id)


def list_archived_projects(data_dir) -> list[Project]:
    """列出 ``archive/`` 下的项目（按项目 ID 排序）。"""
    directory = storage.archive_dir(data_dir)
    if not directory.is_dir():
        return []
    projects: list[Project] = []
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        text = storage.read_text_safe(path)
        if text is None:
            continue
        projects.append(parser.parse_project(text, path.stem))
    return projects


def list_projects(data_dir, *, status: str | None = None) -> list[Project]:
    """列出项目；``status`` 为 ``None`` 时返回全部。"""
    projects: list[Project] = []
    for project_id in storage.list_project_ids(data_dir):
        try:
            project = load_project(data_dir, project_id)
        except ProjectNotFound:  # pragma: no cover - 竞态：刚被删除
            continue
        if status is None or project.status == status:
            projects.append(project)
    return projects


def create_project(
    data_dir,
    project_id: str,
    title: str,
    *,
    status: str = "active",
    stage: str | None = None,
    deadline: Date | None = None,
    current: str = "",
    next_text: str = "",
) -> Project:
    """创建项目。项目 ID 必须显式给出且合法。"""
    if not is_valid_project_id(project_id):
        raise ValueError(f"非法的项目 ID：{project_id!r}")
    if status not in PROJECT_STATUSES:
        raise ValueError(f"未知状态：{status!r}")
    path = storage.project_path(data_dir, project_id)
    if path.exists():
        raise FileExistsError(f"项目已存在：{project_id}")
    text = parser.render_new_project(
        project_id,
        title,
        status=status,
        stage=stage,
        deadline=deadline,
        current=current,
        next_text=next_text,
    )
    storage.write_text(path, text)
    return parser.parse_project(text, project_id)


def archive_project(data_dir, project_id: str) -> Path:
    """把项目文件移动到 ``archive/``，返回归档路径。

    归档不是删除，文件仍在数据目录内，只是不再出现在项目列表中。
    """
    source = storage.project_path(data_dir, project_id)
    if not source.is_file():
        raise ProjectNotFound(project_id)
    target = storage.archive_path(data_dir, project_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"归档中已存在：{target.name}")
    os.replace(source, target)
    return target


def unarchive_project(data_dir, project_id: str) -> Path:
    """把项目从 ``archive/`` 移回 ``projects/``，返回项目文件路径。"""
    source = storage.archive_path(data_dir, project_id)
    if not source.is_file():
        raise ProjectNotFound(project_id)
    target = storage.project_path(data_dir, project_id)
    if target.exists():
        raise FileExistsError(f"项目中已存在：{target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    return target


def delete_project(data_dir, project_id: str) -> None:
    """删除项目文件（不可撤销）。"""
    path = storage.project_path(data_dir, project_id)
    if not path.is_file():
        raise ProjectNotFound(project_id)
    path.unlink()


def delete_archived_project(data_dir, project_id: str) -> None:
    """删除归档中的项目文件（不可撤销）。"""
    path = storage.archive_path(data_dir, project_id)
    if not path.is_file():
        raise ProjectNotFound(project_id)
    path.unlink()


def forget_project(data_dir, project_id: str, *, day: Date | None = None) -> None:
    """项目被删除/归档后，清理对它的“今日重点”引用（只改当天文件）。"""
    day = day or Date.today()
    path = storage.day_path(data_dir, day)
    text = storage.read_text_if_exists(path)
    if text is None:
        return
    if parser.parse_day(text, day).focus == project_id:
        storage.write_text_if_changed(path, parser.set_day_focus(text, None))


def _edit(data_dir, project_id: str, edit: Callable[[str], str]) -> Project:
    path = storage.project_path(data_dir, project_id)
    if not path.is_file():
        raise ProjectNotFound(project_id)
    new_text = edit(storage.read_text(path))
    storage.write_text_if_changed(path, new_text)
    return parser.parse_project(new_text, project_id)


# --------------------------------------------------------------------------- #
# 单字段修改
# --------------------------------------------------------------------------- #
def set_title(data_dir, project_id: str, title: str) -> Project:
    return _edit(data_dir, project_id, lambda t: parser.set_project_title(t, title))


def set_status(data_dir, project_id: str, status: str) -> Project:
    if status not in PROJECT_STATUSES:
        raise ValueError(f"未知状态：{status!r}")
    return _edit(data_dir, project_id, lambda t: parser.set_project_status(t, status))


def set_stage(data_dir, project_id: str, stage: str | None) -> Project:
    return _edit(data_dir, project_id, lambda t: parser.set_project_stage(t, stage))


def set_deadline(data_dir, project_id: str, deadline: Date | None) -> Project:
    return _edit(
        data_dir, project_id, lambda t: parser.set_project_deadline(t, deadline)
    )


def set_current(data_dir, project_id: str, current: str) -> Project:
    return _edit(
        data_dir, project_id, lambda t: parser.set_project_current(t, current)
    )


def set_next(data_dir, project_id: str, next_text: str) -> Project:
    return _edit(
        data_dir, project_id, lambda t: parser.set_project_next(t, next_text)
    )


# --------------------------------------------------------------------------- #
# Touch：项目推进（最核心的操作）
# --------------------------------------------------------------------------- #
def touch(
    data_dir,
    project_id: str,
    *,
    day: Date | None = None,
    note: str | None = None,
) -> Project:
    """标记"今天推进了该项目"。

    1. 在今日文件 ``## Projects`` 中标记该项目；
    2. 在项目 ``## Log`` 中插入今日记录；
    3. 备注可选，可为空。

    同日重复逻辑：当天已有任意 Log 记录时，无备注 touch 不再新增空日志；
    带备注 touch 始终允许追加。
    """
    day = day or Date.today()
    if not project_exists(data_dir, project_id):
        raise ProjectNotFound(project_id)

    # 1. 今日文件
    day_path = storage.day_path(data_dir, day)
    day_text = storage.read_text_if_exists(day_path)
    if day_text is None:
        day_text = parser.render_new_day(day)
    storage.write_text_if_changed(
        day_path, parser.add_day_project(day_text, project_id)
    )

    # 2. 项目 Log
    project_path = storage.project_path(data_dir, project_id)
    project_text = storage.read_text(project_path)
    project = parser.parse_project(project_text, project_id)

    note_text = (note or "").strip()
    already_today = any(entry.date == day for entry in project.log)

    if note_text:
        new_text = parser.append_project_log(project_text, day, note_text)
    elif not already_today:
        new_text = parser.append_project_log(project_text, day)
    else:
        new_text = project_text

    storage.write_text_if_changed(project_path, new_text)
    return parser.parse_project(new_text, project_id)


# --------------------------------------------------------------------------- #
# Focus：今日重点
# --------------------------------------------------------------------------- #
def set_focus(data_dir, project_id: str, *, day: Date | None = None) -> str:
    """设置今日 Focus；一天只能有一个，直接覆盖。"""
    if not project_exists(data_dir, project_id):
        raise ProjectNotFound(project_id)
    day = day or Date.today()
    day_path = storage.day_path(data_dir, day)
    day_text = storage.read_text_if_exists(day_path)
    if day_text is None:
        day_text = parser.render_new_day(day)
    storage.write_text_if_changed(day_path, parser.set_day_focus(day_text, project_id))
    return project_id


def clear_focus(data_dir, *, day: Date | None = None) -> None:
    day = day or Date.today()
    day_path = storage.day_path(data_dir, day)
    day_text = storage.read_text_if_exists(day_path)
    if day_text is None:
        day_text = parser.render_new_day(day)
    storage.write_text_if_changed(day_path, parser.set_day_focus(day_text, None))
