#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${REPO_OWNER:-JackLuo1980}"
REPO_NAME="${REPO_NAME:-xboard-node-tools}"
REPO_BRANCH="${REPO_BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/xboard-node-tools}"
BIN_LINK="${BIN_LINK:-/usr/local/bin/xboard-nodes}"
TMP_DIR="$(mktemp -d)"
ARCHIVE_URL="https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz/refs/heads/${REPO_BRANCH}"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少依赖命令: $1" >&2
    exit 1
  fi
}

need_cmd curl
need_cmd tar
need_cmd python3

echo "==> 下载 ${REPO_OWNER}/${REPO_NAME}@${REPO_BRANCH}"
curl -fsSL "$ARCHIVE_URL" -o "$TMP_DIR/repo.tar.gz"

echo "==> 解压安装包"
tar -xzf "$TMP_DIR/repo.tar.gz" -C "$TMP_DIR"
EXTRACTED_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name "${REPO_NAME}-*" | head -n 1)"

if [[ -z "${EXTRACTED_DIR:-}" || ! -d "$EXTRACTED_DIR" ]]; then
  echo "无法找到解压目录" >&2
  exit 1
fi

echo "==> 安装到 ${INSTALL_DIR}"
mkdir -p "$(dirname "$INSTALL_DIR")"
rm -rf "$INSTALL_DIR"
mv "$EXTRACTED_DIR" "$INSTALL_DIR"

echo "==> 创建命令入口 ${BIN_LINK}"
mkdir -p "$(dirname "$BIN_LINK")"
cat > "$BIN_LINK" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec python3 "${INSTALL_DIR}/xboard_nodes.py" "\$@"
EOF
chmod +x "$BIN_LINK"

echo
echo "安装完成。"
echo "现在可以直接运行:"
echo "  xboard-nodes"
echo
echo "如果你想直接进入某个流程，也可以："
echo "  xboard-nodes --mode probe"
echo "  xboard-nodes --mode import"
