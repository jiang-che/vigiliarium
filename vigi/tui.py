"""curses TUI。

本层只负责 curses、页面、键盘事件与显示，**不直接操作文件**，
一律调用 projects / days / review 的业务 API。

中文宽字符按 ``unicodedata.east_asian_width`` 计算显示宽度，截断时不破坏 CJK。
"""

from __future__ import annotations

import curses
import locale
import os
import shlex
import shutil
import subprocess
import sys
from datetime import date

from . import days, projects, review, storage, ui_text
from .models import PROJECT_STATUSES, ROUTINES
from .textwidth import char_width, display_width, pad, truncate, truncate_left

#: 视为"退出当前页面"的按键；"EOF" 表示终端输入被关闭。
_QUIT_KEYS = ("q", "Q", "ESC", "EOF")


def addstr(win, y: int, x: int, text: str, width: int | None = None, attr: int = 0) -> None:
    """在指定位置安全绘制文本；超出边界或宽字符越界时自动截断。"""
    height, w = win.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= w:
        return
    available = w - x
    if width is not None:
        available = min(available, width)
    if available <= 0:
        return
    text = truncate(str(text), available)
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


# --------------------------------------------------------------------------- #
# 应用
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, stdscr, data_dir) -> None:
        self.stdscr = stdscr
        self.data_dir = data_dir
        self.today = date.today()
        self.projects: list = []
        self.archived: list = []
        self.focus_id: str | None = None
        self.focus_project = None
        self.day = None
        self.index = 0
        self.review_index = 0
        self.archive_index = 0
        self.show_all = False
        self.view_id: str | None = None
        self.message: str | None = None
        self.dirty = True
        self.help_offset = 0
        self.week_offset = 0
        self.detail_offset = 0
        self.detail_view_id: str | None = None
        self.color = {"title": 0, "ok": 0, "warn": 0, "focus": 0}

    # ----- 生命周期 -------------------------------------------------------- #
    def _init_colors(self) -> None:
        """初始化少量颜色；终端不支持时全部退化为默认颜色。"""
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            curses.use_default_colors()
        except curses.error:
            return

        def pair(index: int, fg: int) -> int:
            try:
                curses.init_pair(index, fg, -1)
                return curses.color_pair(index)
            except curses.error:
                return 0

        self.color["title"] = pair(1, curses.COLOR_CYAN)
        self.color["ok"] = pair(2, curses.COLOR_GREEN)
        self.color["warn"] = pair(3, curses.COLOR_YELLOW)
        self.color["focus"] = pair(4, curses.COLOR_MAGENTA)

    def _title_attr(self) -> int:
        return self.color["title"] | curses.A_BOLD

    def _draw_segments(self, y: int, x: int, segments, width: int) -> None:
        """在同一行按段绘制，每段可有不同属性。"""
        cur = x
        for text, attr in segments:
            addstr(self.stdscr, y, cur, text, width - (cur - x), attr)
            cur += display_width(text)

    def run(self) -> int:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.keypad(True)
        self._init_colors()
        errors = (OSError, UnicodeDecodeError, projects.ProjectNotFound)
        screen: str | None = "home"
        while screen is not None:
            if self.dirty:
                # 先清标记，避免读取失败时陷入忙循环
                self.dirty = False
                try:
                    self._load_home()
                except errors as exc:
                    self.message = ui_text.TUI["operation_failed"].format(error=exc)
            try:
                if screen == "home":
                    screen = self.home()
                elif screen == "project":
                    screen = self.project_screen()
                elif screen == "archive":
                    screen = self.archive_screen()
                elif screen == "archive_project":
                    screen = self.project_screen(archived=True)
                elif screen == "review":
                    screen = self.review_screen()
                elif screen == "week":
                    screen = self.week_screen()
                elif screen == "help":
                    screen = self.help_screen()
                else:
                    screen = None
            except errors as exc:
                # 单个操作失败不应该让界面崩溃
                self.message = ui_text.TUI["operation_failed"].format(error=exc)
                screen = "home"
        return 0

    @staticmethod
    def _window(count: int, selected: int, capacity: int) -> tuple[int, int]:
        """返回需要绘制的下标区间 ``[start, end)``，保证选中项可见。"""
        if count <= 0 or capacity <= 0:
            return 0, 0
        selected = min(max(0, selected), count - 1)
        start = max(0, selected - capacity + 1)
        end = min(count, start + capacity)
        start = max(0, end - capacity)
        return start, end

    def _load_archive(self) -> None:
        self.archived = projects.list_archived_projects(self.data_dir)
        if self.archived:
            self.archive_index = min(max(0, self.archive_index), len(self.archived) - 1)
        else:
            self.archive_index = 0

    # ----- 数据 ------------------------------------------------------------ #
    def _load_home(self) -> None:
        self.day = days.load_day(self.data_dir, self.today)
        status = None if self.show_all else "active"
        report = review.review_all(self.data_dir, status=status)
        focus_id = self.day.focus

        def sort_key(item):
            is_focus = 0 if item.project_id == focus_id else 1
            days_since = item.days_since if item.days_since is not None else 10**9
            return (is_focus, -days_since)

        self.projects = sorted(report.projects, key=sort_key)
        self.focus_id = focus_id
        self.focus_project = None
        if focus_id and projects.project_exists(self.data_dir, focus_id):
            self.focus_project = projects.load_project(self.data_dir, focus_id)
        if self.projects:
            self.index = min(max(0, self.index), len(self.projects) - 1)
        else:
            self.index = 0

    def _recent(self, days_since: int | None) -> str:
        if days_since is None:
            return ui_text.format_days_since(None) + " !"
        text = ui_text.format_days_since(days_since)
        if days_since > review.STALE_DAYS:
            text += " !"
        return text

    def _selected(self):
        if not self.projects:
            return None
        return self.projects[self.index]

    # ----- 绘制基元 -------------------------------------------------------- #
    def _header(self, right: str = "") -> None:
        _, w = self.stdscr.getmaxyx()
        addstr(self.stdscr, 0, 1, ui_text.APP_TITLE, w - 3, self._title_attr())
        if right:
            addstr(self.stdscr, 0, max(1, w - display_width(right) - 2), right, w - 2)
        addstr(self.stdscr, 1, 0, "─" * (w - 1), w - 1)

    def _footer(self, text: str) -> None:
        height, w = self.stdscr.getmaxyx()
        addstr(self.stdscr, height - 2, 0, "─" * (w - 1), w - 1)
        addstr(self.stdscr, height - 1, 1, text, w - 2, curses.A_DIM)
        self.message = None

    # ----- 按键 ------------------------------------------------------------ #
    def _get_key(self) -> str | None:
        try:
            ch = self.stdscr.get_wch()
        except curses.error:
            # 通常是输入流被关闭（EOF），当作退出信号，避免死循环。
            return "EOF"
        if isinstance(ch, int):
            return {
                curses.KEY_UP: "UP",
                curses.KEY_DOWN: "DOWN",
                curses.KEY_LEFT: "LEFT",
                curses.KEY_RIGHT: "RIGHT",
                curses.KEY_ENTER: "ENTER",
                curses.KEY_BACKSPACE: "BACKSPACE",
                curses.KEY_RESIZE: "RESIZE",
            }.get(ch)
        if ch in ("\n", "\r"):
            return "ENTER"
        if ch in ("\x7f", "\b"):
            return "BACKSPACE"
        if ch == "\x1b":
            return "ESC"
        return ch

    def _prompt(self, label: str, initial: str = "", context: str = "") -> str | None:
        """在最后一行做单行输入；Enter 返回内容，Esc 返回 None。

        ``context`` 非空时显示在倒数第二行，避免长标题把输入内容挤掉。
        """
        height, w = self.stdscr.getmaxyx()
        buffer: list[str] = list(initial)
        available = w - 2
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        try:
            while True:
                if context:
                    addstr(self.stdscr, height - 2, 0, " " * (w - 1), w - 1)
                    addstr(self.stdscr, height - 2, 1, context, w - 2)
                full = label + "".join(buffer)
                if display_width(full) > available:
                    full = "…" + truncate_left(full, available - 1)
                addstr(self.stdscr, height - 1, 0, " " * (w - 1), w - 1)
                addstr(self.stdscr, height - 1, 1, full, available, self._title_attr())
                self.stdscr.refresh()
                key = self._get_key()
                if key is None:
                    continue
                if key == "ENTER":
                    return "".join(buffer)
                if key in ("ESC", "EOF"):
                    return None
                if key == "BACKSPACE":
                    if buffer:
                        buffer.pop()
                    continue
                if len(key) == 1 and key.isprintable():
                    buffer.append(key)
        finally:
            try:
                curses.curs_set(0)
            except curses.error:
                pass

    def _confirm(self, label: str, context: str = "") -> bool:
        """在最后一行显示确认提示，按 y / Y 返回 True。"""
        height, w = self.stdscr.getmaxyx()
        if context:
            addstr(self.stdscr, height - 2, 0, " " * (w - 1), w - 1)
            addstr(self.stdscr, height - 2, 1, context, w - 2)
        addstr(self.stdscr, height - 1, 0, " " * (w - 1), w - 1)
        addstr(self.stdscr, height - 1, 1, label, w - 2, self._title_attr())
        self.stdscr.refresh()
        return self._get_key() in ("y", "Y")

    # ----- 首页 ------------------------------------------------------------ #
    def home(self) -> str | None:
        self.stdscr.erase()
        height, w = self.stdscr.getmaxyx()
        self._header(self.today.isoformat())

        y = 3
        addstr(self.stdscr, y, 1, ui_text.TUI["home_focus"], w - 3, self._title_attr())
        y += 1
        if self.focus_project is None:
            addstr(self.stdscr, y, 3, ui_text.TUI["no_focus"], w - 5)
            y += 1
        else:
            addstr(
                self.stdscr, y, 3, "> " + self.focus_project.title, w - 5,
                self.color["focus"] | curses.A_BOLD,
            )
            y += 1
            if self.focus_project.current:
                first = self.focus_project.current.splitlines()[0]
                addstr(self.stdscr, y, 5, first, w - 7, curses.A_DIM)
                y += 1
        y += 1

        addstr(self.stdscr, y, 1, ui_text.TUI["home_routine"], w - 3, self._title_attr())
        y += 1
        segments = []
        for index, name in enumerate(ROUTINES):
            done = self.day.routines.get(name)
            if index:
                segments.append(("   ", 0))
            segments.append(
                (
                    "✓ " if done else "○ ",
                    self.color["ok"] if done else curses.A_DIM,
                )
            )
            segments.append((ui_text.routine_name(name), 0))
        self._draw_segments(y, 3, segments, w - 5)
        y += 2

        addstr(self.stdscr, y, 1, ui_text.TUI["home_notes"], w - 3, self._title_attr())
        y += 1
        if self.day.notes:
            shown = self.day.notes[:3]
            for note in shown:
                if y >= height - 2:
                    break
                addstr(self.stdscr, y, 3, "· " + note, w - 5)
                y += 1
            if len(self.day.notes) > len(shown):
                addstr(
                    self.stdscr,
                    y,
                    3,
                    ui_text.TUI["notes_more"].format(
                        count=len(self.day.notes) - len(shown)
                    ),
                    w - 5,
                )
                y += 1
        else:
            addstr(self.stdscr, y, 3, ui_text.TUI["no_notes"], w - 5)
            y += 1
        y += 1

        project_title = (
            ui_text.TUI["home_projects_all"]
            if self.show_all
            else ui_text.TUI["home_projects"]
        )
        capacity = max(1, (height - 2) - (y + 1))
        start, end = self._window(len(self.projects), self.index, capacity)
        if len(self.projects) > capacity:
            project_title += f"（{start + 1}-{end}/{len(self.projects)}）"
        addstr(self.stdscr, y, 1, project_title, w - 3, self._title_attr())
        y += 1
        if not self.projects:
            addstr(self.stdscr, y, 3, ui_text.TUI["no_projects"], w - 5)
            y += 1
        else:
            for i in range(start, end):
                project = self.projects[i]
                marker = ">" if i == self.index else " "
                title = project.title
                if self.show_all and project.status != "active":
                    title += f"（{ui_text.status_name(project.status)}）"
                recent = self._recent(project.days_since)
                line = f"{marker} {title}"
                gap = w - 4 - display_width(line) - display_width(recent)
                if gap < 1:
                    gap = 1
                main = line + " " * gap
                if i == self.index:
                    addstr(self.stdscr, y, 2, main + recent, w - 3, curses.A_REVERSE)
                else:
                    addstr(self.stdscr, y, 2, main, w - 3)
                    if project.days_since is None or project.days_since > review.STALE_DAYS:
                        recent_attr = self.color["warn"]
                    elif project.days_since == 0:
                        recent_attr = self.color["ok"]
                    else:
                        recent_attr = 0
                    addstr(
                        self.stdscr,
                        y,
                        2 + display_width(main),
                        recent,
                        w - 3 - display_width(main),
                        recent_attr,
                    )
                y += 1

        footer = ui_text.TUI["home_footer"]
        if display_width(footer) > w - 2:
            footer = ui_text.TUI["home_footer_short"]
        if display_width(footer) > w - 2:
            footer = ui_text.TUI["footer_min"]
        self._footer(self.message or footer)
        self.stdscr.refresh()

        key = self._get_key()
        if key in _QUIT_KEYS:
            return None
        if key in ("UP", "k"):
            if self.projects:
                self.index = max(0, self.index - 1)
        elif key in ("DOWN", "j"):
            if self.projects:
                self.index = min(len(self.projects) - 1, self.index + 1)
        elif key == "ENTER":
            selected = self._selected()
            if selected is not None:
                self.view_id = selected.project_id
                return "project"
        elif key == "f":
            selected = self._selected()
            if selected is not None:
                projects.set_focus(self.data_dir, selected.project_id)
                self.message = "已设为重点：" + selected.title
                self.dirty = True
        elif key == "F":
            projects.clear_focus(self.data_dir)
            self.message = ui_text.TUI["focus_cleared"]
            self.dirty = True
        elif key in ("t", "T"):
            selected = self._selected()
            if selected is not None:
                self._touch_dialog(selected)
        elif key in ("n", "N"):
            self._today_note_dialog()
        elif key in ("d", "D"):
            self._routine_dialog()
        elif key in ("e", "E"):
            self._edit_path(storage.day_path(self.data_dir, self.today))
        elif key in ("c", "C"):
            self._new_project_dialog()
        elif key == "a":
            self.show_all = not self.show_all
            self.index = 0
            self.dirty = True
        elif key == "A":
            return "archive"
        elif key == "R":
            self.dirty = True
            self.message = "已重新读取数据"
        elif key == "r":
            return "review"
        elif key == "w":
            self.week_offset = 0
            return "week"
        elif key == "?":
            self.help_offset = 0
            return "help"
        return "home"

    # ----- 项目详情 -------------------------------------------------------- #
    def project_screen(self, archived: bool = False) -> str | None:
        try:
            if archived:
                project = projects.load_archived_project(self.data_dir, self.view_id)
            else:
                project = projects.load_project(self.data_dir, self.view_id)
        except projects.ProjectNotFound:
            self.message = ui_text.TUI["not_found"]
            return "archive" if archived else "home"

        if self.detail_view_id != project.project_id:
            self.detail_offset = 0
            self.detail_view_id = project.project_id

        history = review.project_history(
            self.data_dir, project.project_id, limit=100, archived=archived
        )
        last = review.last_touched_date(self.data_dir, project.project_id)
        recent = ui_text.format_days_since(
            None if last is None else (self.today - last).days
        )

        self.stdscr.erase()
        height, w = self.stdscr.getmaxyx()
        self._header()
        addstr(self.stdscr, 3, 1, project.title, w - 3, self._title_attr())
        addstr(self.stdscr, 2, 0, "─" * (w - 1), w - 1)
        fields = [
            (ui_text.TUI["detail_status"], ui_text.status_name(project.status)),
            (ui_text.TUI["detail_stage"], project.stage or "—"),
            (
                ui_text.TUI["detail_deadline"],
                project.deadline.isoformat() if project.deadline else "—",
            ),
            (ui_text.TUI["detail_recent"], recent),
        ]
        label_w = max(display_width(label) for label, _ in fields)
        y = 4
        for label, value in fields:
            addstr(self.stdscr, y, 1, pad(label, label_w) + "  " + value, w - 3)
            y += 1
        y += 1

        for label, value in (
            (ui_text.TUI["detail_current"], project.current),
            (ui_text.TUI["detail_next"], project.next),
        ):
            addstr(self.stdscr, y, 1, label, w - 3, self._title_attr())
            y += 1
            addstr(self.stdscr, y, 3, value or ui_text.TUI["detail_empty"], w - 5)
            y += 2

        log_capacity = max(1, (height - 2) - (y + 1))
        self.detail_offset = min(
            max(0, self.detail_offset), max(0, len(history) - log_capacity)
        )
        log_title = ui_text.TUI["detail_log"]
        if len(history) > log_capacity:
            last_index = min(len(history), self.detail_offset + log_capacity)
            log_title += f"（{self.detail_offset + 1}-{last_index}/{len(history)}）"
        addstr(self.stdscr, y, 1, log_title, w - 3, self._title_attr())
        y += 1
        if not history:
            addstr(self.stdscr, y, 3, ui_text.TUI["detail_empty"], w - 5)
            y += 1
        else:
            for entry in history[self.detail_offset : self.detail_offset + log_capacity]:
                when = entry.date.isoformat() if entry.date else "—"
                addstr(self.stdscr, y, 3, f"{when}  {entry.note or ''}", w - 5)
                y += 1

        footer = (
            ui_text.TUI["back_footer"] if archived else ui_text.TUI["project_footer"]
        )
        self._footer(self.message or footer)
        self.stdscr.refresh()

        key = self._get_key()
        if key in ("UP", "k"):
            self.detail_offset = max(0, self.detail_offset - 1)
            return "archive_project" if archived else "project"
        if key in ("DOWN", "j"):
            self.detail_offset += 1
            return "archive_project" if archived else "project"
        if archived:
            return "archive" if key in _QUIT_KEYS else "archive_project"
        if key in _QUIT_KEYS:
            return "home"
        if key in ("t", "T", "n", "N"):
            self._touch_dialog(project)
        elif key in ("c", "C"):
            self._edit_text_dialog(project, "current")
        elif key in ("x", "X"):
            self._edit_text_dialog(project, "next")
        elif key in ("e", "E"):
            self._edit_path(storage.project_path(self.data_dir, project.project_id))
        elif key in ("s", "S"):
            self._status_dialog(project)
        elif key in ("d", "D"):
            if self._confirm(
                ui_text.TUI["confirm_delete_label"], context=project.title
            ):
                try:
                    projects.delete_project(self.data_dir, project.project_id)
                    projects.forget_project(self.data_dir, project.project_id)
                    self.message = ui_text.TUI["project_deleted"].format(
                        title=project.title
                    )
                except OSError:
                    self.message = ui_text.TUI["delete_failed"]
                self.dirty = True
                return "home"
        elif key == "A":
            try:
                projects.archive_project(self.data_dir, project.project_id)
                projects.forget_project(self.data_dir, project.project_id)
                self.message = ui_text.TUI["project_archived"].format(
                    title=project.title
                )
            except FileExistsError:
                self.message = ui_text.TUI["archive_exists"].format(
                    project_id=project.project_id
                )
            except OSError:
                self.message = ui_text.TUI["archive_failed"]
            self.dirty = True
            return "home"
        return "project"

    # ----- 回顾 ------------------------------------------------------------ #
    def review_screen(self) -> str | None:
        status = None if self.show_all else "active"
        report = review.review_all(self.data_dir, status=status)
        items = report.projects
        if items:
            self.review_index = min(self.review_index, len(items) - 1)
        else:
            self.review_index = 0

        self.stdscr.erase()
        height, w = self.stdscr.getmaxyx()
        self._header()
        title = (
            ui_text.TUI["review_title_all"]
            if self.show_all
            else ui_text.TUI["review_title"]
        )
        rows = []
        for item in items:
            recent = ui_text.format_days_since(item.days_since)
            if item.days_since is None or item.days_since > review.STALE_DAYS:
                recent += " !"
            rows.append(
                (
                    item.title,
                    recent,
                    item.days_7,
                    item.days_30,
                    ui_text.status_name(item.status),
                )
            )
        lines = ui_text.format_review_table(rows, width=w - 4)
        capacity = max(1, (height - 4) - 5)
        start, end = self._window(len(items), self.review_index, capacity)
        if len(items) > capacity:
            title += f"（{start + 1}-{end}/{len(items)}）"
        addstr(self.stdscr, 3, 1, title, w - 3, self._title_attr())
        y = 5
        if lines:
            addstr(self.stdscr, y, 2, lines[0], w - 3)
            y += 1
        for idx in range(start, end):
            selected = idx == self.review_index
            attr = curses.A_REVERSE if selected else curses.A_NORMAL
            addstr(self.stdscr, y, 2, lines[idx + 1], w - 3, attr)
            y += 1
        y += 1
        if y < height - 2:
            addstr(
                self.stdscr, y, 1, ui_text.CLI["summary_active"].format(count=report.active_count), w - 3
            )
            y += 1
            addstr(
                self.stdscr, y, 1, ui_text.CLI["summary_week"].format(count=report.touched_this_week), w - 3
            )
            y += 1
            addstr(
                self.stdscr, y, 1, ui_text.CLI["summary_stale"].format(count=report.stale_over_7), w - 3
            )
        self._footer(ui_text.TUI["review_footer"])
        self.stdscr.refresh()

        key = self._get_key()
        if key in ("a", "A"):
            self.show_all = not self.show_all
            self.review_index = 0
        elif key in ("UP", "k"):
            if items:
                self.review_index = max(0, self.review_index - 1)
        elif key in ("DOWN", "j"):
            if items:
                self.review_index = min(len(items) - 1, self.review_index + 1)
        elif key == "ENTER":
            if items:
                self.view_id = items[self.review_index].project_id
                return "project"
        elif key in _QUIT_KEYS:
            return "home"
        return "review"

    # ----- 归档 ------------------------------------------------------------ #
    def archive_screen(self) -> str | None:
        self._load_archive()
        items = self.archived
        self.stdscr.erase()
        height, w = self.stdscr.getmaxyx()
        self._header()
        title = ui_text.TUI["archive_title"]
        capacity = max(1, (height - 2) - 5)
        start, end = self._window(len(items), self.archive_index, capacity)
        if len(items) > capacity:
            title += f"（{start + 1}-{end}/{len(items)}）"
        addstr(self.stdscr, 3, 1, title, w - 3, self._title_attr())
        y = 5
        if not items:
            addstr(self.stdscr, y, 3, ui_text.TUI["no_archived_view"], w - 5)
        else:
            for i in range(start, end):
                project = items[i]
                row = (
                    f"{'>' if i == self.archive_index else ' '} "
                    f"{project.title}  [{ui_text.status_name(project.status)}]"
                )
                attr = (
                    curses.A_REVERSE if i == self.archive_index else curses.A_NORMAL
                )
                addstr(self.stdscr, y, 2, row, w - 3, attr)
                y += 1
        self._footer(self.message or ui_text.TUI["archive_footer"])
        self.stdscr.refresh()

        key = self._get_key()
        if key in ("UP", "k"):
            if items:
                self.archive_index = max(0, self.archive_index - 1)
        elif key in ("DOWN", "j"):
            if items:
                self.archive_index = min(len(items) - 1, self.archive_index + 1)
        elif key == "ENTER":
            if items:
                self.view_id = items[self.archive_index].project_id
                return "archive_project"
        elif key in ("u", "U"):
            if items:
                project = items[self.archive_index]
                try:
                    projects.unarchive_project(self.data_dir, project.project_id)
                    self.message = ui_text.TUI["project_unarchived"].format(
                        title=project.title
                    )
                    self.dirty = True
                except FileExistsError:
                    self.message = ui_text.TUI["unarchive_exists"].format(
                        project_id=project.project_id
                    )
                except OSError:
                    self.message = ui_text.TUI["archive_failed"]
        elif key in ("d", "D"):
            if items:
                project = items[self.archive_index]
                if self._confirm(
                    ui_text.TUI["confirm_delete_label"], context=project.title
                ):
                    try:
                        projects.delete_archived_project(
                            self.data_dir, project.project_id
                        )
                        self.message = ui_text.TUI["project_deleted"].format(
                            title=project.title
                        )
                    except OSError:
                        self.message = ui_text.TUI["delete_failed"]
                    self.dirty = True
        elif key in _QUIT_KEYS:
            return "home"
        return "archive"

    # ----- 周回顾 ---------------------------------------------------------- #
    def week_screen(self) -> str | None:
        summary = review.week_summary(self.data_dir, day=self.today)
        self.stdscr.erase()
        height, w = self.stdscr.getmaxyx()
        self._header()
        title = ui_text.CLI["week_title"].format(
            week=summary.week,
            start=summary.monday.isoformat(),
            end=summary.sunday.isoformat(),
        )
        addstr(self.stdscr, 3, 1, ui_text.TUI["week_title"] + "  " + title, w - 3, self._title_attr())
        y = 5
        addstr(self.stdscr, y, 1, ui_text.CLI["routine_header"], w - 3, self._title_attr())
        y += 1
        for name in ROUTINES:
            marks = summary.routine_days[name]
            line = " ".join("✓" if value else "·" for value in marks)
            addstr(
                self.stdscr,
                y,
                3,
                ui_text.CLI["week_routine_line"].format(
                    name=ui_text.routine_name(name), marks=line, total=sum(marks)
                ),
                w - 5,
            )
            y += 1
        y += 1
        project_rows = sorted(summary.project_days.items())
        id_w = max((display_width(pid) for pid, _ in project_rows), default=0)
        capacity = max(1, (height - 2) - (y + 1))
        self.week_offset = min(
            max(0, self.week_offset), max(0, len(project_rows) - capacity)
        )
        header = ui_text.CLI["week_projects_header"]
        if len(project_rows) > capacity:
            header += (
                f"（{self.week_offset + 1}-{self.week_offset + capacity}"
                f"/{len(project_rows)}）"
            )
        addstr(self.stdscr, y, 1, header, w - 3, self._title_attr())
        y += 1
        for project_id, marks in project_rows[
            self.week_offset : self.week_offset + capacity
        ]:
            line = " ".join("●" if value else "·" for value in marks)
            addstr(
                self.stdscr,
                y,
                3,
                ui_text.CLI["week_project_line"].format(
                    project_id=pad(project_id, id_w), marks=line, total=sum(marks)
                ),
                w - 5,
            )
            y += 1
        self._footer(ui_text.TUI["week_footer"])
        self.stdscr.refresh()
        key = self._get_key()
        if key in ("UP", "k"):
            self.week_offset = max(0, self.week_offset - 1)
        elif key in ("DOWN", "j"):
            self.week_offset = min(
                max(0, len(project_rows) - capacity), self.week_offset + 1
            )
        elif key in _QUIT_KEYS:
            return "home"
        return "week"

    # ----- 帮助 ------------------------------------------------------------ #
    def help_screen(self) -> str | None:
        lines = ui_text.tui_help_lines()
        self.stdscr.erase()
        height, w = self.stdscr.getmaxyx()
        self._header()
        capacity = max(1, (height - 2) - 5)
        self.help_offset = min(
            max(0, self.help_offset), max(0, len(lines) - capacity)
        )
        title = ui_text.TUI["help_title"]
        if len(lines) > capacity:
            title += f"（{self.help_offset + 1}-{self.help_offset + capacity}/{len(lines)}）"
        addstr(self.stdscr, 3, 1, title, w - 3, self._title_attr())
        y = 5
        for line in lines[self.help_offset : self.help_offset + capacity]:
            addstr(self.stdscr, y, 3, line, w - 5)
            y += 1
        self._footer(ui_text.TUI["help_footer"])
        self.stdscr.refresh()
        key = self._get_key()
        if key in ("UP", "k"):
            self.help_offset = max(0, self.help_offset - 1)
        elif key in ("DOWN", "j"):
            self.help_offset = min(max(0, len(lines) - capacity), self.help_offset + 1)
        elif key in _QUIT_KEYS:
            return "home"
        return "help"

    # ----- 对话框 ---------------------------------------------------------- #
    def _touch_dialog(self, project) -> None:
        note = self._prompt(ui_text.TUI["note_label"], context=project.title)
        if note is None:
            self.message = ui_text.TUI["cancelled"]
            return
        projects.touch(self.data_dir, project.project_id, note=note or None)
        self.message = "已推进：" + project.title
        self.dirty = True

    def _today_note_dialog(self) -> None:
        note = self._prompt(ui_text.TUI["today_note_label"])
        if note is None:
            self.message = ui_text.TUI["cancelled"]
            return
        if note:
            days.append_note(self.data_dir, self.today, note)
            self.message = "已记录备注"
            self.dirty = True
        else:
            self.message = ui_text.TUI["note_empty"]

    def _routine_dialog(self) -> None:
        index = 0
        while True:
            self.stdscr.erase()
            _, w = self.stdscr.getmaxyx()
            self._header()
            addstr(self.stdscr, 3, 2, ui_text.TUI["routine_label"], w - 4, self._title_attr())
            for i, name in enumerate(ROUTINES):
                mark = "✓" if self.day.routines.get(name) else "○"
                row = f"{'>' if i == index else ' '} [{mark}] {ui_text.routine_name(name)}"
                addstr(
                    self.stdscr,
                    5 + i,
                    4,
                    row,
                    w - 6,
                    curses.A_REVERSE if i == index else curses.A_NORMAL,
                )
            self._footer(ui_text.TUI["back_footer"])
            self.stdscr.refresh()

            key = self._get_key()
            if key in _QUIT_KEYS or key is None:
                break
            if key in ("UP", "k"):
                index = max(0, index - 1)
            elif key in ("DOWN", "j"):
                index = min(len(ROUTINES) - 1, index + 1)
            elif key in ("ENTER", " "):
                name = ROUTINES[index]
                if self.day.routines.get(name):
                    days.undo(self.data_dir, name)
                else:
                    days.done(self.data_dir, name)
                self.dirty = True
                self._load_home()

    def _status_dialog(self, project) -> None:
        index = PROJECT_STATUSES.index(project.status) if project.status in PROJECT_STATUSES else 0
        while True:
            self.stdscr.erase()
            _, w = self.stdscr.getmaxyx()
            self._header()
            addstr(self.stdscr, 3, 2, ui_text.TUI["status_label"], w - 4, self._title_attr())
            for i, status in enumerate(PROJECT_STATUSES):
                row = f"{'>' if i == index else ' '} {ui_text.status_name(status)}"
                addstr(
                    self.stdscr,
                    5 + i,
                    4,
                    row,
                    w - 6,
                    curses.A_REVERSE if i == index else curses.A_NORMAL,
                )
            self._footer(ui_text.TUI["back_footer"])
            self.stdscr.refresh()

            key = self._get_key()
            if key in _QUIT_KEYS or key is None:
                return
            if key in ("UP", "k"):
                index = max(0, index - 1)
            elif key in ("DOWN", "j"):
                index = min(len(PROJECT_STATUSES) - 1, index + 1)
            elif key == "ENTER":
                projects.set_status(self.data_dir, project.project_id, PROJECT_STATUSES[index])
                self.dirty = True
                return

    def _edit_text_dialog(self, project, field: str) -> None:
        """在项目页内联编辑“当前”或“下一步”（单行；留空即清除）。"""
        if field == "current":
            label = ui_text.TUI["current_label"]
            initial = project.current.replace("\n", " ")
            message = ui_text.TUI["current_updated"]
        else:
            label = ui_text.TUI["next_label"]
            initial = project.next.replace("\n", " ")
            message = ui_text.TUI["next_updated"]

        value = self._prompt(label, initial, context=project.title)
        if value is None:
            self.message = ui_text.TUI["cancelled"]
            return
        value = value.strip()
        if field == "current":
            projects.set_current(self.data_dir, project.project_id, value)
        else:
            projects.set_next(self.data_dir, project.project_id, value)
        self.message = message
        self.dirty = True

    def _new_project_dialog(self) -> None:
        title = self._prompt(ui_text.TUI["new_title_label"])
        if not title:
            self.message = ui_text.TUI["cancelled"]
            return
        project_id = self._prompt(ui_text.TUI["new_id_label"])
        if not project_id:
            self.message = ui_text.TUI["cancelled"]
            return
        stage = self._prompt(ui_text.TUI["new_stage_label"]) or None
        deadline_value = self._prompt(ui_text.TUI["new_deadline_label"]) or ""
        deadline = None
        if deadline_value:
            try:
                deadline = date.fromisoformat(deadline_value)
            except ValueError:
                self.message = ui_text.TUI["invalid_deadline"]
                return
        try:
            projects.create_project(
                self.data_dir, project_id, title, stage=stage, deadline=deadline
            )
        except (ValueError, FileExistsError) as exc:
            self.message = f"创建失败：{exc}"
            return
        self.message = ui_text.TUI["created"].format(title=title)
        self.dirty = True

    def _edit_path(self, path) -> None:
        editor = os.environ.get("EDITOR", "").strip()
        if editor:
            command = shlex.split(editor)
        elif shutil.which("nano"):
            command = ["nano"]
        else:
            self.message = "未设置 $EDITOR"
            return
        path = str(path)
        curses.def_prog_mode()
        curses.endwin()
        try:
            subprocess.call(command + [path])
        except OSError:
            self.message = "无法启动编辑器"
        finally:
            curses.reset_prog_mode()
            self.stdscr.keypad(True)
            self.stdscr.refresh()
        # 外部编辑器可能改动了文件，标记为需要重新读取。
        self.dirty = True


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def run(data_dir) -> int:
    """启动 TUI；非交互式终端时给出提示。"""
    if not sys.stdout.isatty():
        print(ui_text.CLI["tui_notty"])
        return 1
    locale.setlocale(locale.LC_ALL, "")
    try:
        return curses.wrapper(lambda stdscr: App(stdscr, data_dir).run())
    except KeyboardInterrupt:
        return 130
