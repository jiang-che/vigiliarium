"""中文 UI 固定文本集中管理。

所有固定界面字符串都应放这里，不要散落在业务逻辑中。
MVP 不实现语言切换，但集中管理为未来国际化保留可能性。
"""

from __future__ import annotations

from .textwidth import display_width, pad

#: 应用显示标题。命令行名称是 ``vigi``，标题首字母大写。
APP_TITLE = "Vigiliarium"

#: 固定中文界面文本。
UI_TEXT = {
    # 页面 / 区块标题
    "today_focus": "今日重点",
    "routine": "例行事项",
    "projects": "项目",
    "review": "项目回顾",
    "recent": "最近推进",
    "current_stage": "当前阶段",
    "next_step": "下一步",
    # 状态显示
    "done": "已完成",
    "paused": "已暂停",
    # 例行事项中文名（文件中始终用英文）
    "routine_names": {
        "reading": "阅读",
        "writing": "写作",
        "email": "邮件",
        "admin": "杂务",
    },
    # 项目状态：英文存储值 → 中文显示
    "status_names": {
        "active": "进行中",
        "waiting": "等待中",
        "paused": "已暂停",
        "idea": "想法",
        "done": "已完成",
    },
}


def status_name(status: str) -> str:
    """状态英文值 → 中文显示（未知值原样返回）。"""
    return UI_TEXT["status_names"].get(status, status)


def routine_name(name: str) -> str:
    """例行事项英文键 → 中文显示（未知值原样返回）。"""
    return UI_TEXT["routine_names"].get(name, name)


def format_days_since(days: int | None) -> str:
    """把“距今天数”格式化为中文（今天 / 1 天前 / … / 从未）。"""
    if days is None:
        return "从未"
    if days <= 0:
        return "今天"
    return f"{days} 天前"


_REVIEW_COLUMNS = (9, 4, 5, 6)  # 最近 / 7 天 / 30 天 / 状态


def _join_row(cells, widths, gap: int) -> str:
    return (" " * gap).join(pad(cell, w) for cell, w in zip(cells, widths))


def format_review_table(rows, width: int = 80) -> list[str]:
    """把回顾数据排版为按显示宽度对齐的若干行。

    ``rows`` 每项为 ``(title, recent, days7, days30, status)``。
    """
    gap = 2
    fixed = sum(_REVIEW_COLUMNS) + gap * (len(_REVIEW_COLUMNS) + 1)
    title_w = max(12, width - fixed)
    widths = (title_w, *_REVIEW_COLUMNS)
    lines = [_join_row(("项目", "最近", "7 天", "30 天", "状态"), widths, gap)]
    for title, recent, days7, days30, status in rows:
        lines.append(
            _join_row(
                (str(title), str(recent), str(days7), str(days30), str(status)),
                widths,
                gap,
            )
        )
    return lines


def format_projects_table(rows, width: int = 80) -> list[str]:
    """把项目列表排版为对齐的若干行。``rows`` 每项为 ``(id, title, status, recent)``。"""
    gap = 2
    id_w = max([display_width("ID")] + [display_width(r[0]) for r in rows])
    status_w = max([display_width("状态")] + [display_width(r[2]) for r in rows])
    recent_w = max([display_width("最近")] + [display_width(r[3]) for r in rows])
    title_w = max(8, width - id_w - status_w - recent_w - gap * 3)
    widths = (id_w, title_w, status_w, recent_w)
    lines = [_join_row(("ID", "标题", "状态", "最近"), widths, gap)]
    for project_id, title, status, recent in rows:
        lines.append(_join_row((project_id, title, status, recent), widths, gap))
    return lines


# --------------------------------------------------------------------------- #
# CLI 文案（命令用英文，输出用中文）
# --------------------------------------------------------------------------- #
CLI_DESCRIPTION = "Vigiliarium — 面向学者的极简项目推进 TUI 工具"
CLI_DIR_HELP = "数据目录（默认 ~/.local/share/vigi；也可用环境变量 vigi_DIR）"
CLI_DATA_DIR = "数据目录：{path}"

CLI = {
    # 通用
    "unknown_project": "错误：找不到项目 {project_id}",
    "did_you_mean": "你是否指 {suggestion}？",
    "no_projects": "（没有项目）",
    # projects
    "projects_header": "项目：",
    # touch / focus
    "touched": "已推进：{title}",
    "focus_set": "今日重点：{title}",
    # routine
    "routine_done": "已打卡：{name}",
    "routine_undone": "已取消：{name}",
    # current / next
    "current_set": "已更新“当前”：{text}",
    "next_set": "已更新“下一步”：{text}",
    "note_added": "已添加今日备注：{text}",
    "empty": "（空）",
    # info
    "info_label_version": "版本",
    "info_label_dir": "数据目录",
    "info_label_source": "来源",
    "info_label_exists": "目录状态",
    "info_source_cli": "--dir 参数",
    "info_source_env": "环境变量 {var}",
    "info_source_default": "默认目录",
    "exists_yes": "已存在",
    "exists_no": "不存在（运行其他命令时会自动创建）",
    # new
    "created": "已创建项目：{title}（{project_id}）",
    "project_exists": "错误：项目已存在：{project_id}",
    "confirm_delete": "确定删除项目“{title}”（{project_id}）？此操作不可撤销，输入 y 确认：",
    "deleted": "已删除项目：{title}",
    "archived": "已归档项目：{project_id}",
    "unarchived": "已取消归档：{project_id}",
    "archive_exists": "错误：归档中已存在同名文件：{project_id}",
    "unarchive_exists": "错误：项目中已存在同名文件：{project_id}",
    "archived_header": "归档：",
    "no_archived": "（归档中没有项目）",
    "note_empty": "错误：备注不能为空",
    "invalid_deadline": "错误：截止日期格式应为 YYYY-MM-DD：{value}",
    "prompt_title": "项目标题：",
    "prompt_id": "项目 ID：",
    "prompt_stage": "当前阶段（可空）：",
    "prompt_deadline": "截止日期（可空，YYYY-MM-DD）：",
    "cancelled": "已取消。",
    # edit
    "edit_missing_file": "错误：找不到项目文件：{path}",
    "edit_no_editor": "错误：未设置 $EDITOR 且找不到 nano",
    # review
    "review_title": "项目回顾",
    "review_title_all": "项目回顾（全部）",
    "focus_cleared": "已清除今日重点",
    "focus_need_id": "错误：请给出项目 ID，或用 --clear 清除今日重点",
    # today
    "today_title": "今日记录（{date}）",
    "today_focus": "今日重点：{text}",
    "today_routines": "例行事项：{marks}",
    "today_projects": "接触项目：{text}",
    "today_notes": "备注：",
    "today_note_line": "  - {note}",
    "none": "（无）",
    "unset": "（未设置）",
    "summary_active": "活跃项目：{count}",
    "summary_week": "本周碰过：{count}",
    "summary_stale": "超过 7 天未碰：{count}",
    # weekly review
    "week_title": "第 {week} 周（{start} ~ {end}）",
    "routine_header": "例行事项",
    "week_routine_line": "  {name}  {marks}   {total}/7",
    "week_projects_header": "项目",
    "week_project_line": "  {project_id}  {marks}   {total} 天",
    # TUI 启动失败（非交互式终端）
    "tui_notty": "当前不是交互式终端，无法启动 TUI。请使用 CLI 子命令：vigi --help",
}

# TUI 文案
TUI = {
    # 区块
    "home_focus": "今日重点",
    "home_routine": "例行事项",
    "home_notes": "今日备注",
    "home_projects": "项目",
    "home_projects_all": "项目（全部）",
    "no_focus": "（未设置，按 f 选择某个项目）",
    "no_notes": "（无，按 n 添加，按 e 编辑）",
    "notes_more": "…（还有 {count} 条，按 e 编辑）",
    "no_projects": "（还没有项目，按 c 新建）",
    # 项目详情
    "detail_status": "状态",
    "detail_stage": "阶段",
    "detail_deadline": "截止",
    "detail_recent": "最近推进",
    "detail_current": "当前",
    "detail_next": "下一步",
    "detail_log": "最近记录",
    "detail_empty": "（空）",
    # 状态中文（复用 UI_TEXT["status_names"]）
    # 页面标题
    "review_title": "项目回顾",
    "review_title_all": "项目回顾（全部）",
    "week_title": "周回顾",
    "archive_title": "归档项目",
    "help_title": "帮助",
    "not_found": "（项目不存在）",
    "no_archived_view": "（归档中没有项目）",
    "archive_footer": "Enter 查看  u 取消归档  d 删除  q 返回",
    "project_unarchived": "已取消归档：{title}",
    "unarchive_exists": "已存在同名项目：{project_id}",
    "delete_failed": "删除失败",
    "archive_failed": "归档失败",
    "operation_failed": "操作失败：{error}",
    "note_empty": "未输入内容",
    "focus_cleared": "已清除今日重点",
    "confirm_delete_label": "确定删除此项目？不可撤销，按 y 确认：",
    "project_deleted": "已删除：{title}",
    "project_archived": "已归档：{title}",
    "archive_exists": "归档中已存在同名文件：{project_id}",
    # 提示
    "touch_label": "推进项目：",
    "note_label": "备注（可留空，Enter 保存 / Esc 取消）：",
    "today_note_label": "今日备注（Enter 保存 / Esc 取消）：",
    "new_title_label": "项目标题：",
    "new_id_label": "项目 ID：",
    "new_stage_label": "当前阶段（可留空）：",
    "new_deadline_label": "截止日期（可留空，YYYY-MM-DD）：",
    "status_label": "修改状态（Enter 选择 / Esc 取消）：",
    "routine_label": "例行事项（Space 切换 / Esc 关闭）：",
    "current_label": "当前（Enter 保存 / Esc 取消，留空即清除）：",
    "next_label": "下一步（Enter 保存 / Esc 取消，留空即清除）：",
    "current_updated": "已更新“当前”",
    "next_updated": "已更新“下一步”",
    "invalid_deadline": "截止日期格式应为 YYYY-MM-DD",
    "created": "已创建：{title}",
    "cancelled": "已取消",
    # 首页脚注
    "home_footer": "Enter 查看  f 重点  t 推进  d 打卡  n 备注  e 编辑  c 新建  a 全部  A 归档  r 回顾  w 周回顾  R 重读  ? 帮助  q 退出",
    "home_footer_short": "Enter 查看  t 推进  f 重点  d 打卡  n 备注  e 编辑  A 归档  ? 帮助  q 退出",
    "footer_min": "? 帮助  q 退出",
    "project_footer": "t 推进  n 备注  c 当前  x 下一步  s 状态  e 编辑  d 删除  A 归档  q 返回",
    "review_footer": "Enter 查看  a 全部/进行中  q 返回",
    "back_footer": "q 返回",
}

#: 帮助页内容：(按键, 说明)。说明为 None 表示分节标题；(None, None) 表示空行。
TUI_HELP = [
    ("首页", None),
    ("↑↓ / j k", "移动选择"),
    ("Enter", "查看项目详情"),
    ("f", "设为今日重点"),
    ("F", "清除今日重点"),
    ("t", "推进选中项目"),
    ("d", "例行事项打卡"),
    ("n", "添加今日备注"),
    ("e", "用 $EDITOR 编辑今日记录"),
    ("c", "新建项目"),
    ("a", "切换 进行中 / 全部项目"),
    ("A", "查看归档项目"),
    ("r", "项目回顾（Enter 可打开项目）"),
    ("w", "周回顾"),
    ("R", "重新读取数据（外部改动后）"),
    ("?", "帮助"),
    ("q", "退出"),
    (None, None),
    ("项目页", None),
    ("t", "推进"),
    ("n", "推进并写备注"),
    ("c", "修改“当前”"),
    ("x", "修改“下一步”"),
    ("s", "修改状态"),
    ("e", "用 $EDITOR 编辑整份文件"),
    ("d", "删除项目（需确认）"),
    ("A", "归档项目"),
    ("q", "返回"),
]


def tui_help_lines() -> list[str]:
    """生成按显示宽度对齐的帮助页文本行。"""
    key_w = max(display_width(key) for key, _ in TUI_HELP if key)
    lines: list[str] = []
    for key, desc in TUI_HELP:
        if key is None and desc is None:
            lines.append("")
        elif desc is None:
            lines.append(key + "：")
        else:
            lines.append(pad(key, key_w) + "  " + desc)
    lines.append("")
    lines.append("本工具只用纯文本 Markdown 记录；数据目录中的文件随时可手动编辑。")
    return lines
