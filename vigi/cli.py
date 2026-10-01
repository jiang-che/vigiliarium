"""Vigiliarium 命令行入口。

命令名用英文，输出用中文。无子命令时进入 TUI。
退出码：0 成功 / 1 一般错误 / 2 参数错误。
"""

from __future__ import annotations

import argparse
import difflib
import os
import shlex
import shutil
import subprocess
import sys
from datetime import date

from . import __version__, days, parser, projects, review, storage, tui, ui_text
from .models import ROUTINES
from .textwidth import display_width, pad

# --------------------------------------------------------------------------- #
# 输出辅助
# --------------------------------------------------------------------------- #
def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _report_unknown_project(data_dir, project_id: str) -> int:
    _err(ui_text.CLI["unknown_project"].format(project_id=project_id))
    known = storage.list_project_ids(data_dir)
    matches = difflib.get_close_matches(project_id, known, n=1, cutoff=0.6)
    if matches:
        _err(ui_text.CLI["did_you_mean"].format(suggestion=matches[0]))
    return 1


def _prompt(label: str) -> str | None:
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


# --------------------------------------------------------------------------- #
# 子命令实现
# --------------------------------------------------------------------------- #
def cmd_projects(args, data_dir) -> int:
    if args.archived:
        return _print_archived(data_dir)
    report = review.review_all(data_dir, status=None)
    items = sorted(report.projects, key=lambda item: item.project_id)
    if not items:
        print(ui_text.CLI["no_projects"])
        return 0
    rows = [
        (
            item.project_id,
            item.title,
            ui_text.status_name(item.status),
            ui_text.format_days_since(item.days_since),
        )
        for item in items
    ]
    print(ui_text.CLI["projects_header"])
    width = shutil.get_terminal_size((80, 24)).columns
    for line in ui_text.format_projects_table(rows, width=width - 2):
        print("  " + line)
    return 0


def _print_archived(data_dir) -> int:
    ids = sorted(
        path.stem
        for path in storage.archive_dir(data_dir).glob("*.md")
        if path.is_file()
    )
    if not ids:
        print(ui_text.CLI["no_archived"])
        return 0
    rows = []
    for project_id in ids:
        text = storage.read_text_safe(storage.archive_path(data_dir, project_id))
        if text is None:
            continue
        project = parser.parse_project(text, project_id)
        rows.append(
            (
                project_id,
                project.title,
                ui_text.status_name(project.status),
                "—",
            )
        )
    print(ui_text.CLI["archived_header"])
    width = shutil.get_terminal_size((80, 24)).columns
    for line in ui_text.format_projects_table(rows, width=width - 2):
        print("  " + line)
    return 0


def cmd_focus(args, data_dir) -> int:
    if args.clear:
        projects.clear_focus(data_dir)
        print(ui_text.CLI["focus_cleared"])
        return 0
    if not args.project_id:
        _err(ui_text.CLI["focus_need_id"])
        return 2
    projects.set_focus(data_dir, args.project_id)
    project = projects.load_project(data_dir, args.project_id)
    print(ui_text.CLI["focus_set"].format(title=project.title))
    return 0


def cmd_touch(args, data_dir) -> int:
    project = projects.touch(data_dir, args.project_id, note=args.message)
    print(ui_text.CLI["touched"].format(title=project.title))
    return 0


def cmd_current(args, data_dir) -> int:
    projects.set_current(data_dir, args.project_id, args.text)
    print(ui_text.CLI["current_set"].format(text=args.text or ui_text.CLI["empty"]))
    return 0


def cmd_next(args, data_dir) -> int:
    projects.set_next(data_dir, args.project_id, args.text)
    print(ui_text.CLI["next_set"].format(text=args.text or ui_text.CLI["empty"]))
    return 0


def cmd_info(args, data_dir) -> int:
    data_dir, source_key = storage.resolve_data_dir_with_source(
        getattr(args, "data_dir", None)
    )
    env_value = os.environ.get(storage.ENV_VAR)
    source = {
        "cli": ui_text.CLI["info_source_cli"],
        "env": ui_text.CLI["info_source_env"].format(var=storage.ENV_VAR),
        "default": ui_text.CLI["info_source_default"],
    }[source_key]
    rows = [
        (ui_text.CLI["info_label_version"], __version__),
        (ui_text.CLI["info_label_dir"], str(data_dir)),
        (ui_text.CLI["info_label_source"], source),
        (storage.ENV_VAR, env_value or ui_text.CLI["unset"]),
        (
            ui_text.CLI["info_label_exists"],
            ui_text.CLI["exists_yes"]
            if os.path.isdir(data_dir)
            else ui_text.CLI["exists_no"],
        ),
    ]
    label_w = max(display_width(label) for label, _ in rows)
    for label, value in rows:
        print(pad(label, label_w) + "  " + value)
    return 0


def cmd_today(args, data_dir) -> int:
    record = days.load_day(data_dir, date.today(), create=False)
    print(ui_text.CLI["today_title"].format(date=record.date.isoformat()))
    print()

    if record.focus and projects.project_exists(data_dir, record.focus):
        focus_text = projects.load_project(data_dir, record.focus).title
    else:
        focus_text = record.focus or ui_text.CLI["unset"]
    print(ui_text.CLI["today_focus"].format(text=focus_text))

    marks = "  ".join(
        f"{'✓' if record.routines.get(name) else '○'} {ui_text.routine_name(name)}"
        for name in ROUTINES
    )
    print(ui_text.CLI["today_routines"].format(marks=marks))
    print(
        ui_text.CLI["today_projects"].format(
            text="、".join(sorted(record.projects)) or ui_text.CLI["none"]
        )
    )

    print()
    print(ui_text.CLI["today_notes"])
    if record.notes:
        for note in record.notes:
            print(ui_text.CLI["today_note_line"].format(note=note))
    else:
        print("  " + ui_text.CLI["none"])
    return 0


def cmd_note(args, data_dir) -> int:
    if not args.text.strip():
        _err(ui_text.CLI["note_empty"])
        return 2
    days.append_note(data_dir, date.today(), args.text)
    print(ui_text.CLI["note_added"].format(text=args.text))
    return 0


def cmd_archive(args, data_dir) -> int:
    try:
        projects.archive_project(data_dir, args.project_id)
    except FileExistsError:
        _err(ui_text.CLI["archive_exists"].format(project_id=args.project_id))
        return 1
    projects.forget_project(data_dir, args.project_id)
    print(ui_text.CLI["archived"].format(project_id=args.project_id))
    return 0


def cmd_unarchive(args, data_dir) -> int:
    try:
        projects.unarchive_project(data_dir, args.project_id)
    except FileExistsError:
        _err(ui_text.CLI["unarchive_exists"].format(project_id=args.project_id))
        return 1
    print(ui_text.CLI["unarchived"].format(project_id=args.project_id))
    return 0


def cmd_delete(args, data_dir) -> int:
    project = projects.load_project(data_dir, args.project_id)
    if not args.yes:
        prompt = ui_text.CLI["confirm_delete"].format(
            title=project.title, project_id=project.project_id
        )
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            answer = ""
        if answer not in ("y", "yes", "是"):
            print(ui_text.CLI["cancelled"])
            return 0
    projects.delete_project(data_dir, args.project_id)
    projects.forget_project(data_dir, args.project_id)
    print(ui_text.CLI["deleted"].format(title=project.title))
    return 0


def cmd_done(args, data_dir) -> int:
    days.done(data_dir, args.routine)
    print(ui_text.CLI["routine_done"].format(name=ui_text.routine_name(args.routine)))
    return 0


def cmd_undo(args, data_dir) -> int:
    days.undo(data_dir, args.routine)
    print(ui_text.CLI["routine_undone"].format(name=ui_text.routine_name(args.routine)))
    return 0


def cmd_new(args, data_dir) -> int:
    interactive = sys.stdin.isatty()

    title = args.title if args.title is not None else _prompt(ui_text.CLI["prompt_title"])
    if not title:
        print(ui_text.CLI["cancelled"])
        return 2

    project_id = (
        args.project_id
        if args.project_id is not None
        else _prompt(ui_text.CLI["prompt_id"])
    )
    if not project_id:
        print(ui_text.CLI["cancelled"])
        return 2

    stage = args.stage
    if stage is None and interactive:
        stage = _prompt(ui_text.CLI["prompt_stage"]) or None

    deadline_value = args.deadline
    if deadline_value is None and interactive:
        deadline_value = _prompt(ui_text.CLI["prompt_deadline"]) or ""
    deadline = None
    if deadline_value:
        try:
            deadline = date.fromisoformat(deadline_value)
        except ValueError:
            _err(ui_text.CLI["invalid_deadline"].format(value=deadline_value))
            return 2

    try:
        project = projects.create_project(
            data_dir, project_id, title, stage=stage, deadline=deadline
        )
    except FileExistsError:
        _err(ui_text.CLI["project_exists"].format(project_id=project_id))
        return 1
    except ValueError as exc:
        _err(f"错误：{exc}")
        return 2

    print(ui_text.CLI["created"].format(title=project.title, project_id=project.project_id))
    return 0


def cmd_edit(args, data_dir) -> int:
    path = storage.project_path(data_dir, args.project_id)
    if not path.is_file():
        raise projects.ProjectNotFound(args.project_id)

    editor = os.environ.get("EDITOR", "").strip()
    if editor:
        command = shlex.split(editor)
    elif shutil.which("nano"):
        command = ["nano"]
    else:
        _err(ui_text.CLI["edit_no_editor"])
        return 1

    try:
        code = subprocess.call(command + [str(path)])
    except FileNotFoundError:
        _err(ui_text.CLI["edit_no_editor"])
        return 1
    return 0 if code == 0 else 1


def _print_review(data_dir, *, show_all: bool = False) -> int:
    report = review.review_all(data_dir, status=None if show_all else "active")
    print(
        ui_text.CLI["review_title_all"] if show_all else ui_text.CLI["review_title"]
    )
    print()
    rows = []
    for item in report.projects:
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
    width = shutil.get_terminal_size((80, 24)).columns
    for line in ui_text.format_review_table(rows, width=width - 4):
        print("  " + line)
    print()
    print(ui_text.CLI["summary_active"].format(count=report.active_count))
    print(ui_text.CLI["summary_week"].format(count=report.touched_this_week))
    print(ui_text.CLI["summary_stale"].format(count=report.stale_over_7))
    return 0


def _print_week(data_dir) -> int:
    summary = review.week_summary(data_dir)
    print(
        ui_text.CLI["week_title"].format(
            week=summary.week,
            start=summary.monday.isoformat(),
            end=summary.sunday.isoformat(),
        )
    )
    print()
    print(ui_text.CLI["routine_header"])
    for name in ROUTINES:
        marks = summary.routine_days[name]
        line = " ".join("✓" if value else "·" for value in marks)
        print(
            ui_text.CLI["week_routine_line"].format(
                name=ui_text.routine_name(name), marks=line, total=sum(marks)
            )
        )
    print()
    print(ui_text.CLI["week_projects_header"])
    project_rows = sorted(summary.project_days.items())
    if not project_rows:
        print("  " + ui_text.CLI["no_projects"])
    id_w = max((display_width(pid) for pid, _ in project_rows), default=0)
    for project_id, marks in project_rows:
        line = " ".join("●" if value else "·" for value in marks)
        print(
            ui_text.CLI["week_project_line"].format(
                project_id=pad(project_id, id_w), marks=line, total=sum(marks)
            )
        )
    return 0


def cmd_review(args, data_dir) -> int:
    if args.week:
        return _print_week(data_dir)
    return _print_review(data_dir, show_all=args.all)


# --------------------------------------------------------------------------- #
# 参数解析
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dir",
        dest="data_dir",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help=ui_text.CLI_DIR_HELP,
    )
    parser = argparse.ArgumentParser(
        prog="vigi",
        description=ui_text.CLI_DESCRIPTION,
        parents=[common],
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("projects", parents=[common], help="列出项目")
    p.add_argument("--archived", action="store_true", help="列出已归档项目")
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("focus", parents=[common], help="设置今日重点")
    p.add_argument("project_id", nargs="?")
    p.add_argument("--clear", action="store_true", help="清除今日重点")
    p.set_defaults(func=cmd_focus)

    p = sub.add_parser("touch", parents=[common], help="标记今日推进")
    p.add_argument("project_id")
    p.add_argument("-m", "--message", default=None, help="可选备注")
    p.set_defaults(func=cmd_touch)

    p = sub.add_parser("current", parents=[common], help="设置项目的“当前”")
    p.add_argument("project_id")
    p.add_argument("text", help="新内容；传空字符串可清除")
    p.set_defaults(func=cmd_current)

    p = sub.add_parser("next", parents=[common], help="设置项目的“下一步”")
    p.add_argument("project_id")
    p.add_argument("text", help="新内容；传空字符串可清除")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("info", parents=[common], help="显示数据目录等运行信息")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("today", parents=[common], help="查看今日记录（重点 / 例行 / 项目 / 备注）")
    p.set_defaults(func=cmd_today)

    p = sub.add_parser("note", parents=[common], help="添加今日备注")
    p.add_argument("text")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("done", parents=[common], help="例行事项打卡")
    p.add_argument("routine", choices=list(ROUTINES))
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("undo", parents=[common], help="取消例行事项打卡")
    p.add_argument("routine", choices=list(ROUTINES))
    p.set_defaults(func=cmd_undo)

    p = sub.add_parser("review", parents=[common], help="项目回顾")
    p.add_argument("--week", action="store_true", help="查看本周回顾")
    p.add_argument("--all", action="store_true", help="包含非进行中的项目")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("new", parents=[common], help="创建项目")
    p.add_argument("title", nargs="?", default=None)
    p.add_argument("--id", dest="project_id", default=None, help="项目 ID（必须显式给出）")
    p.add_argument("--stage", default=None)
    p.add_argument("--deadline", default=None, help="YYYY-MM-DD")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("edit", parents=[common], help="使用 $EDITOR 编辑项目文件")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("archive", parents=[common], help="归档项目（移动到 archive/）")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("unarchive", parents=[common], help="取消归档（移回 projects/）")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_unarchive)

    p = sub.add_parser("delete", parents=[common], help="删除项目（需确认）")
    p.add_argument("project_id")
    p.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    p.set_defaults(func=cmd_delete)

    return parser


def _configure_io() -> None:
    """在非 UTF-8 locale 下也能正确输出中文（errors 用 replace 兜底）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_io()
    parser = build_parser()
    args = parser.parse_args(argv)

    data_dir = storage.resolve_data_dir(getattr(args, "data_dir", None))
    if getattr(args, "command", None) != "info":
        try:
            storage.ensure_data_dirs(data_dir)
        except OSError as exc:
            _err(f"错误：无法使用数据目录 {data_dir}：{exc}")
            return 1

    func = getattr(args, "func", None)
    try:
        if func is None:
            return tui.run(data_dir)
        return func(args, data_dir)
    except projects.ProjectNotFound as exc:
        return _report_unknown_project(data_dir, exc.project_id)
    except days.UnknownRoutine as exc:
        _err(f"错误：未知例行事项 {exc}")
        return 2
    except (OSError, UnicodeDecodeError) as exc:
        _err(f"错误：读写数据目录失败：{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
