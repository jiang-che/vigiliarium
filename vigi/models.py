"""领域模型，使用标准库 ``dataclasses``。

不使用 ORM。解析后的只读视图；写回逻辑在 ``parser`` 中基于原始文本保守进行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

#: 例行事项的规范键（文件中用英文名，CLI 用英文，TUI 显示中文）。
ROUTINES: tuple[str, ...] = ("reading", "writing", "email", "admin")

#: 例行事项在 Markdown 文件中的英文显示名。
ROUTINE_DISPLAY: dict[str, str] = {
    "reading": "Reading",
    "writing": "Writing",
    "email": "Email",
    "admin": "Admin",
}

#: 项目状态固定支持值。
PROJECT_STATUSES: tuple[str, ...] = ("active", "waiting", "paused", "idea", "done")


@dataclass
class ProjectLogEntry:
    """``## Log`` 中的一条记录，例如 ``- 2026-10-01 — 第二节基本改完。``"""

    date: date | None
    note: str | None
    raw: str


@dataclass
class Project:
    """一个项目，对应 ``projects/<project_id>.md``。"""

    project_id: str
    title: str
    status: str = "active"
    stage: str | None = None
    deadline: date | None = None
    current: str = ""
    next: str = ""
    log: list[ProjectLogEntry] = field(default_factory=list)


@dataclass
class DayRecord:
    """一天的记录，对应 ``days/YYYY-MM-DD.md``。"""

    date: date
    focus: str | None = None
    routines: dict[str, bool] = field(default_factory=dict)
    projects: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
