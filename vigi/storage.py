"""数据目录、路径与安全文件读写。

只负责路径与文件 I/O，不涉及业务逻辑，便于单独测试。
所有重写型操作走 ``write_text``：写临时文件 → flush+fsync → 原子替换。
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Mapping

#: 数据目录环境变量名。
ENV_VAR = "vigi_DIR"

#: 默认数据目录（相对于用户主目录）。
DEFAULT_RELATIVE_DIR = Path(".local/share/vigi")

#: 数据目录下需要存在的子目录。
SUBDIRS = ("projects", "days", "archive")

#: 文件编码（UTF-8）。
ENCODING = "utf-8"


# --------------------------------------------------------------------------- #
# 数据目录解析
# --------------------------------------------------------------------------- #
def resolve_data_dir_with_source(
    cli_dir: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
) -> tuple[Path, str]:
    """解析数据目录并返回来源（``"cli"`` / ``"env"`` / ``"default"``）。

    优先级：

    1. 命令行参数 ``--dir``（``cli_dir``）；
    2. 环境变量 ``vigi_DIR``；
    3. 默认目录 ``~/.local/share/vigi``。

    参数 ``env`` 与 ``home`` 仅用于测试注入；生产代码留空即可。
    """
    if cli_dir is not None and str(cli_dir) != "":
        return Path(cli_dir).expanduser(), "cli"

    environ = os.environ if env is None else env
    env_value = environ.get(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser(), "env"

    if home is not None:
        return Path(home) / DEFAULT_RELATIVE_DIR, "default"
    return Path.home() / DEFAULT_RELATIVE_DIR, "default"


def resolve_data_dir(
    cli_dir: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
) -> Path:
    """按优先级解析最终数据目录（只返回路径）。"""
    return resolve_data_dir_with_source(cli_dir, env=env, home=home)[0]


def ensure_data_dirs(data_dir: str | os.PathLike[str]) -> Path:
    """确保数据目录及其子目录存在，返回数据目录。"""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (data_dir / name).mkdir(parents=True, exist_ok=True)
    return data_dir


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
def projects_dir(data_dir: str | os.PathLike[str]) -> Path:
    return Path(data_dir) / "projects"


def days_dir(data_dir: str | os.PathLike[str]) -> Path:
    return Path(data_dir) / "days"


def archive_dir(data_dir: str | os.PathLike[str]) -> Path:
    return Path(data_dir) / "archive"


def project_path(data_dir: str | os.PathLike[str], project_id: str) -> Path:
    """项目文件路径：``projects/<project_id>.md``。"""
    return projects_dir(data_dir) / f"{project_id}.md"


def archive_path(data_dir: str | os.PathLike[str], project_id: str) -> Path:
    """归档文件路径：``archive/<project_id>.md``。"""
    return archive_dir(data_dir) / f"{project_id}.md"


def day_path(data_dir: str | os.PathLike[str], day: date) -> Path:
    """每日文件路径：``days/YYYY-MM-DD.md``。"""
    return days_dir(data_dir) / f"{day.isoformat()}.md"


def list_project_ids(data_dir: str | os.PathLike[str]) -> list[str]:
    """列出 ``projects/`` 下的所有项目 ID（按文件名，升序）。"""
    directory = projects_dir(data_dir)
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.md") if p.is_file())


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #
def read_text(path: str | os.PathLike[str]) -> str:
    """按 UTF-8 读取文本文件。"""
    return Path(path).read_text(encoding=ENCODING)


def read_text_if_exists(path: str | os.PathLike[str]) -> str | None:
    """存在则按 UTF-8 读取，否则返回 ``None``。"""
    p = Path(path)
    if not p.exists():
        return None
    return p.read_text(encoding=ENCODING)


def read_text_safe(path: str | os.PathLike[str]) -> str | None:
    """批量扫描时用：读不到或不是 UTF-8 时返回 ``None``，不让单个坏文件中断整体。"""
    try:
        return read_text(path)
    except (OSError, UnicodeDecodeError):
        return None


def write_text(path: str | os.PathLike[str], text: str) -> None:
    """原子写入文本。

    步骤：在目标目录内创建临时文件 → 写入 → ``flush`` + ``fsync`` → ``os.replace``。
    任一步失败都会清理临时文件，且不会破坏原有内容。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".tmp-", suffix=".md"
    )
    try:
        with os.fdopen(fd, "w", encoding=ENCODING, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_text_if_changed(path: str | os.PathLike[str], text: str) -> bool:
    """内容有变化才原子写入；返回是否真的写入了。

    避免无意义地刷新文件 mtime，降低文件同步工具产生冲突的概率。
    """
    existing = read_text_if_exists(path)
    if existing == text:
        return False
    write_text(path, text)
    return True
