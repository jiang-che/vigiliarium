"""Markdown 解析与保守写回。

设计原则：

- **宽容解析**：遇到不认识的字段或段落不报错、不丢弃。
- **保守写回**：只改动目标字段/段落所在的行，保留其余原文与用户自定义内容。
- 写回函数接收原始文本并返回新文本；内容无变化时返回**完全相同的字符串**，
  调用方可据此用 ``storage.write_text_if_changed`` 避免无意义写盘。
"""

from __future__ import annotations

import re
from datetime import date

from .models import (
    ROUTINES,
    ROUTINE_DISPLAY,
    DayRecord,
    Project,
    ProjectLogEntry,
)

# ``Status: active`` / ``Focus: frankfurt-hps`` 之类的头部字段。
_HEADER_RE = re.compile(r"^(?P<key>[A-Za-z]+)\s*:\s*(?P<value>.*)$")
_H1_RE = re.compile(r"^#\s+(?P<title>.*?)\s*$")
_H2_RE = re.compile(r"^##\s+(?P<name>.+?)\s*$")
# 段落边界：一级或二级标题（``###`` 不计入，视为段落内容）。
_HEADING_BOUNDARY_RE = re.compile(r"^#{1,2}\s")
_CHECKBOX_RE = re.compile(r"^-\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s*(?P<text>.*)$")
_LOG_DATE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})(?:\s*[—–-]\s*(?P<note>.*))?$"
)

_HEADER_KEYS = ("Status", "Stage", "Deadline")


# --------------------------------------------------------------------------- #
# 文本行工具（精确保留行结构，不做隐式重排）
# --------------------------------------------------------------------------- #
def _split(text: str) -> list[str]:
    """按 ``\\n`` 切分，保留末尾空串以精确保留结尾换行。"""
    return text.split("\n")


def _join(lines: list[str]) -> str:
    return "\n".join(lines)


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _field_line(key: str, value: str | None) -> str:
    """渲染头部字段；空值渲染为 ``Key:``。"""
    if value:
        return f"{key}: {value}"
    return f"{key}:"


def _section_block(name: str, body: str = "") -> list[str]:
    """渲染一个 ``## name`` 段落块；空正文只保留标题行。"""
    if body:
        return [f"## {name}", "", *body.splitlines()]
    return [f"## {name}"]


def _join_sections(parts: list[list[str]]) -> str:
    """用空行连接若干块，保证段落之间恰好一个空行。"""
    out: list[str] = []
    for i, part in enumerate(parts):
        if i:
            out.append("")
        out.extend(part)
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# 段落定位与编辑
# --------------------------------------------------------------------------- #
def _find_section(lines: list[str], name: str) -> tuple[int, int, int] | None:
    """定位 ``## name`` 段落，返回 ``(heading_idx, body_start, body_end)``。"""
    target = name.casefold()
    for i, line in enumerate(lines):
        match = _H2_RE.match(line)
        if match and match.group("name").strip().casefold() == target:
            start = i + 1
            end = start
            while end < len(lines) and not _HEADING_BOUNDARY_RE.match(lines[end]):
                end += 1
            return i, start, end
    return None


def _section_lines(lines: list[str], name: str) -> list[str]:
    loc = _find_section(lines, name)
    if loc is None:
        return []
    _, start, end = loc
    return lines[start:end]


def _section_text(lines: list[str], name: str) -> str:
    """返回段落正文（去掉首尾空行），多行用 ``\\n`` 连接。"""
    body = list(_section_lines(lines, name))
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body).strip()


def _ensure_section(lines: list[str], name: str) -> None:
    """确保 ``## name`` 段落存在（不存在则在文末追加）。"""
    if _find_section(lines, name) is not None:
        return
    if lines and lines[-1].strip():
        lines.append("")
    lines.extend([f"## {name}", ""])


def _set_section_body(lines: list[str], name: str, body_lines: list[str]) -> None:
    """用 ``body_lines`` 替换段落正文，保持标题行与段落间空行结构。"""
    _ensure_section(lines, name)
    loc = _find_section(lines, name)
    assert loc is not None
    _, start, end = loc
    formatted = ["", *body_lines, ""] if body_lines else [""]
    lines[start:end] = formatted


def _append_to_section(lines: list[str], name: str, new_lines: list[str]) -> None:
    """把 ``new_lines`` 追加到段落末尾（追加型，不重排已有内容）。"""
    _ensure_section(lines, name)
    loc = _find_section(lines, name)
    assert loc is not None
    _, start, end = loc
    body = lines[start:end]
    head = 0
    while head < len(body) and not body[head].strip():
        head += 1
    tail = len(body)
    while tail > head and not body[tail - 1].strip():
        tail -= 1
    insert_at = start + tail
    lines[insert_at:insert_at] = new_lines

    # 若紧随其后就是下一个标题，确保插入内容与标题之间留一个空行。
    after = insert_at + len(new_lines)
    if (
        after < len(lines)
        and _HEADING_BOUNDARY_RE.match(lines[after])
        and lines[after - 1].strip()
    ):
        lines.insert(after, "")


def _prepend_to_section(lines: list[str], name: str, new_lines: list[str]) -> None:
    """把 ``new_lines`` 插到段落正文开头（跳过标题后的空行）。"""
    _ensure_section(lines, name)
    loc = _find_section(lines, name)
    assert loc is not None
    _, start, end = loc
    body = lines[start:end]
    head = 0
    while head < len(body) and not body[head].strip():
        head += 1
    insert_at = start + head
    lines[insert_at:insert_at] = new_lines


def _set_header_field(lines: list[str], key: str, value: str | None) -> None:
    """设置 ``Key: value`` 头部字段（只改该行，必要时插入）。"""
    rendered = _field_line(key, value)
    key_cf = key.casefold()

    for i, line in enumerate(lines):
        match = _HEADER_RE.match(line)
        if match and match.group("key").casefold() == key_cf:
            if lines[i] != rendered:
                lines[i] = rendered
            return

    # 插入到已有头部字段之后
    header_indices = [
        i
        for i, line in enumerate(lines)
        if (m := _HEADER_RE.match(line))
        and m.group("key").casefold() in {k.casefold() for k in _HEADER_KEYS}
    ]
    if header_indices:
        lines.insert(max(header_indices) + 1, rendered)
        return

    # 其次插入到一级标题之后
    for i, line in enumerate(lines):
        if _H1_RE.match(line):
            lines.insert(i + 1, rendered)
            return

    lines.insert(0, rendered)


# --------------------------------------------------------------------------- #
# 项目：解析
# --------------------------------------------------------------------------- #
def parse_project(text: str, project_id: str) -> Project:
    """把项目 Markdown 解析为 :class:`Project`（宽容解析）。"""
    lines = _split(text)

    title = ""
    status: str | None = None
    stage: str | None = None
    deadline: date | None = None

    for line in lines:
        h1 = _H1_RE.match(line)
        if h1 and not title:
            title = h1.group("title").strip()
            continue
        header = _HEADER_RE.match(line)
        if header:
            key = header.group("key").casefold()
            value = header.group("value").strip()
            if key == "status" and value:
                status = value
            elif key == "stage":
                stage = value or None
            elif key == "deadline":
                deadline = _parse_date(value)

    current = _section_text(lines, "Current")
    next_text = _section_text(lines, "Next")
    log = _parse_log(_section_lines(lines, "Log"))

    return Project(
        project_id=project_id,
        title=title,
        status=status or "active",
        stage=stage,
        deadline=deadline,
        current=current,
        next=next_text,
        log=log,
    )


def _parse_log(body: list[str]) -> list[ProjectLogEntry]:
    entries: list[ProjectLogEntry] = []
    for line in body:
        bullet = _BULLET_RE.match(line)
        if not bullet:
            continue
        rest = bullet.group("text").strip()
        if not rest:
            continue
        match = _LOG_DATE_RE.match(rest)
        if match:
            note = match.group("note")
            entries.append(
                ProjectLogEntry(
                    date=_parse_date(match.group("date")),
                    note=note.strip() if note else None,
                    raw=line,
                )
            )
        else:
            entries.append(ProjectLogEntry(date=None, note=rest, raw=line))
    return entries


# --------------------------------------------------------------------------- #
# 项目：保守写回
# --------------------------------------------------------------------------- #
def set_project_title(text: str, title: str) -> str:
    lines = _split(text)
    for i, line in enumerate(lines):
        if _H1_RE.match(line):
            rendered = f"# {title}"
            if lines[i] != rendered:
                lines[i] = rendered
            return _join(lines)
    lines.insert(0, f"# {title}")
    return _join(lines)


def set_project_status(text: str, status: str) -> str:
    lines = _split(text)
    _set_header_field(lines, "Status", status)
    return _join(lines)


def set_project_stage(text: str, stage: str | None) -> str:
    lines = _split(text)
    _set_header_field(lines, "Stage", stage)
    return _join(lines)


def set_project_deadline(text: str, deadline: date | None) -> str:
    lines = _split(text)
    _set_header_field(lines, "Deadline", deadline.isoformat() if deadline else None)
    return _join(lines)


def set_project_current(text: str, current: str) -> str:
    lines = _split(text)
    _set_section_body(lines, "Current", current.splitlines() if current else [])
    return _join(lines)


def set_project_next(text: str, next_text: str) -> str:
    lines = _split(text)
    _set_section_body(lines, "Next", next_text.splitlines() if next_text else [])
    return _join(lines)


def append_project_log(
    text: str, entry_date: date, note: str | None = None
) -> str:
    """新增一条 Log 记录。

    插到 ``## Log`` 正文顶部，保持“最新在上”的倒序格式。
    """
    lines = _split(text)
    rendered = f"- {entry_date.isoformat()}"
    if note:
        rendered += f" — {note}"
    _prepend_to_section(lines, "Log", [rendered])
    return _join(lines)


def render_new_project(
    project_id: str,
    title: str,
    *,
    status: str = "active",
    stage: str | None = None,
    deadline: date | None = None,
    current: str = "",
    next_text: str = "",
) -> str:
    """渲染一个新的项目文件。``project_id`` 仅用于签名对称。"""
    del project_id  # 由调用方决定文件名
    header = [
        f"# {title}",
        "",
        _field_line("Status", status),
        _field_line("Stage", stage),
        _field_line("Deadline", deadline.isoformat() if deadline else None),
    ]
    parts = [
        header,
        _section_block("Current", current),
        _section_block("Next", next_text),
        _section_block("Log"),
    ]
    return _join_sections(parts) + "\n"


# --------------------------------------------------------------------------- #
# 每日记录：解析
# --------------------------------------------------------------------------- #
def parse_day(text: str, day: date) -> DayRecord:
    """把每日 Markdown 解析为 :class:`DayRecord`（宽容解析）。"""
    lines = _split(text)

    focus: str | None = None
    for line in lines:
        header = _HEADER_RE.match(line)
        if header and header.group("key").casefold() == "focus":
            focus = header.group("value").strip() or None
            break

    routines: dict[str, bool] = {name: False for name in ROUTINES}
    for line in _section_lines(lines, "Routine"):
        match = _CHECKBOX_RE.match(line)
        if match:
            key = match.group("text").strip().casefold()
            routines[key] = match.group("mark").lower() == "x"

    projects: set[str] = set()
    for line in _section_lines(lines, "Projects"):
        match = _CHECKBOX_RE.match(line)
        if match and match.group("mark").lower() == "x":
            projects.add(match.group("text").strip())

    notes: list[str] = []
    for line in _section_lines(lines, "Notes"):
        bullet = _BULLET_RE.match(line)
        if bullet and bullet.group("text").strip():
            notes.append(bullet.group("text").strip())

    return DayRecord(
        date=day,
        focus=focus,
        routines=routines,
        projects=projects,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# 每日记录：保守写回
# --------------------------------------------------------------------------- #
def set_day_focus(text: str, focus: str | None) -> str:
    lines = _split(text)
    _set_header_field(lines, "Focus", focus)
    return _join(lines)


def set_routine(text: str, name: str, done: bool) -> str:
    """打卡 / 取消某个例行事项。``name`` 大小写不敏感。"""
    lines = _split(text)
    target = name.casefold()
    mark = "x" if done else " "

    loc = _find_section(lines, "Routine")
    if loc is not None:
        _, start, end = loc
        for i in range(start, end):
            match = _CHECKBOX_RE.match(lines[i])
            if match and match.group("text").strip().casefold() == target:
                rendered = f"- [{mark}] {match.group('text').strip()}"
                if lines[i] != rendered:
                    lines[i] = rendered
                return _join(lines)

    display = ROUTINE_DISPLAY.get(target, name.capitalize())
    _append_to_section(lines, "Routine", [f"- [{mark}] {display}"])
    return _join(lines)


def add_day_project(text: str, project_id: str) -> str:
    """确保今日 ``## Projects`` 中存在该项目并标记为已接触。"""
    lines = _split(text)

    loc = _find_section(lines, "Projects")
    if loc is not None:
        _, start, end = loc
        for i in range(start, end):
            match = _CHECKBOX_RE.match(lines[i])
            if match and match.group("text").strip() == project_id:
                if match.group("mark").lower() != "x":
                    lines[i] = f"- [x] {project_id}"
                return _join(lines)

    _append_to_section(lines, "Projects", [f"- [x] {project_id}"])
    return _join(lines)


def append_day_note(text: str, note: str) -> str:
    lines = _split(text)
    _append_to_section(lines, "Notes", [f"- {note}"])
    return _join(lines)


def render_new_day(day: date) -> str:
    """渲染一个新的每日文件。"""
    header = [f"# {day.isoformat()}", "", _field_line("Focus", None)]
    routine_body = "\n".join(f"- [ ] {ROUTINE_DISPLAY[name]}" for name in ROUTINES)
    parts = [
        header,
        _section_block("Routine", routine_body),
        _section_block("Projects"),
        _section_block("Notes"),
    ]
    return _join_sections(parts) + "\n"
