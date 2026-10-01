"""Nuitka 单文件编译入口。

不要直接用 ``vigi/__main__.py`` 编译：那里使用相对导入，在 Nuitka 的
单文件/模块模式下会因缺少父包而失败。这里使用绝对导入，并把整个 ``vigi``
包交给 Nuitka 静态收集。

另外，容器/最小系统常见的 POSIX(C) locale 下，命令行参数会被以非 UTF-8 的
文件系统编码解码（并带 surrogateescape），导致中文参数无法写盘。这里在启动时
强制 UTF-8 处理，使二进制在任意 locale 下都能正确处理中文。
"""

from __future__ import annotations

import os
import sys


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    # 若 argv 以非 UTF-8 编码解码，从原始字节恢复。
    recovered: list[str] = []
    for arg in sys.argv:
        try:
            recovered.append(os.fsencode(arg).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            recovered.append(arg)
    sys.argv = recovered


_force_utf8()

from vigi.cli import main  # noqa: E402  （须在 _force_utf8 之后导入）

if __name__ == "__main__":
    sys.exit(main())
