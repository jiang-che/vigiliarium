#!/usr/bin/env bash
# 在容器内用 Nuitka 编译单文件二进制。
# 由 packaging/build.sh 在构建镜像中调用，工作目录为项目根 /src。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
rm -rf dist build

python3 -m nuitka \
    --onefile \
    --assume-yes-for-downloads \
    --include-package=vigi \
    --include-module=_curses \
    --python-flag=no_docstrings \
    --no-deployment-flag=self-execution \
    --output-filename=vigi \
    --output-dir=dist \
    --remove-output \
    packaging/entry.py

echo "---- dist ----"
ls -l dist
