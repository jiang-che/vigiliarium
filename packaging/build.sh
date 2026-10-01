#!/usr/bin/env bash
# 构建单一二进制文件。
#
#   用法：bash packaging/build.sh
#   环境变量：
#     VIGI_CONTAINER_RUNTIME  容器运行时（默认 podman，可设 docker）
#     VIGI_BUILD_IMAGE        构建镜像标签
#
# 产物：<项目根>/dist/vigi （单个 ELF，目标机器无需安装 Python）
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
runtime="${VIGI_CONTAINER_RUNTIME:-podman}"
image="${VIGI_BUILD_IMAGE:-localhost/vigiliarium-builder:1}"

if ! command -v "$runtime" >/dev/null 2>&1; then
    echo "错误：找不到容器运行时 $runtime" >&2
    exit 1
fi

echo "==> 构建镜像 $image（利用层缓存）"
"$runtime" build -f "$here/Containerfile" -t "$image" "$here"

echo "==> 在容器内运行 Nuitka"
mkdir -p "$root/dist"
"$runtime" run --rm \
    -v "$root":/src:Z \
    -w /src \
    "$image" \
    bash packaging/nuitka-build.sh

echo "==> 产物：$root/dist/vigi"
file "$root/dist/vigi" 2>/dev/null || true
