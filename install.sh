#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${REPO_OWNER:-JackLuo1980}"
REPO_NAME="${REPO_NAME:-xboard-node-tools}"
REPO_BRANCH="${REPO_BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/xboard-node-tools}"
BIN_LINK="${BIN_LINK:-/usr/local/bin/xboard-nodes}"
CONFIG_DIR="${CONFIG_DIR:-$HOME/.config/xboard-node-tools}"
CONFIG_PATH="${CONFIG_PATH:-$CONFIG_DIR/config.json}"
AUTO_RUN="${AUTO_RUN:-true}"
AUTO_MODE="${AUTO_MODE:-menu}"
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

install_sshpass_if_needed() {
  if [[ -z "${XBOARD_DEFAULT_SSH_PASSWORD:-}" ]]; then
    return 0
  fi

  if command -v sshpass >/dev/null 2>&1; then
    return 0
  fi

  echo "==> 检测到预置 SSH 密码，但本机未安装 sshpass，尝试自动安装"

  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y sshpass >/dev/null
    return 0
  fi

  if command -v dnf >/dev/null 2>&1; then
    dnf install -y sshpass >/dev/null
    return 0
  fi

  if command -v yum >/dev/null 2>&1; then
    yum install -y epel-release >/dev/null 2>&1 || true
    yum install -y sshpass >/dev/null
    return 0
  fi

  if command -v apk >/dev/null 2>&1; then
    apk add --no-cache sshpass >/dev/null
    return 0
  fi

  echo "无法自动安装 sshpass，请手工安装后重试。" >&2
  exit 1
}

need_cmd curl
need_cmd tar
need_cmd python3
install_sshpass_if_needed

write_default_config() {
  if [[ -z "${XBOARD_DEFAULT_SSH_HOST:-}" ]]; then
    return 0
  fi

  mkdir -p "$CONFIG_DIR"
  CONFIG_PATH="$CONFIG_PATH" python3 - <<'PY'
import json
import os
from pathlib import Path

config_path = Path(os.environ["CONFIG_PATH"])
if config_path.exists():
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        config = {}
else:
    config = {}

profile = {
    "ssh_host": os.environ.get("XBOARD_DEFAULT_SSH_HOST", ""),
    "ssh_user": os.environ.get("XBOARD_DEFAULT_SSH_USER", "root"),
    "ssh_password": os.environ.get("XBOARD_DEFAULT_SSH_PASSWORD", ""),
    "remote_json_dir": os.environ.get("XBOARD_DEFAULT_REMOTE_JSON_DIR", "/root"),
    "db_host": os.environ.get("XBOARD_DEFAULT_DB_HOST", "127.0.0.1"),
    "db_port": os.environ.get("XBOARD_DEFAULT_DB_PORT", "3306"),
    "db_name": os.environ.get("XBOARD_DEFAULT_DB_NAME", "xboard"),
    "db_user": os.environ.get("XBOARD_DEFAULT_DB_USER", "xboard"),
    "db_password": os.environ.get("XBOARD_DEFAULT_DB_PASSWORD", ""),
    "groups": os.environ.get("XBOARD_DEFAULT_GROUPS", "vip1,vip2,vip3"),
}
config["default_xboard"] = profile
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  echo "==> 已写入默认 Xboard 配置到 ${CONFIG_PATH}"
}

echo "==> 下载 ${REPO_OWNER}/${REPO_NAME}@${REPO_BRANCH}"
curl -fsSL "$ARCHIVE_URL" -o "$TMP_DIR/repo.tar.gz"

echo "==> 解压安装包"
tar --warning=no-timestamp -xzf "$TMP_DIR/repo.tar.gz" -C "$TMP_DIR"
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
write_default_config

echo
echo "安装完成。"
echo "现在可以直接运行:"
echo "  xboard-nodes"
echo
echo "如果你想直接进入某个流程，也可以："
echo "  xboard-nodes --mode export"
echo "  xboard-nodes --mode upload"
echo "  xboard-nodes --mode create"
echo "  xboard-nodes --mode sync"

if [[ "$AUTO_RUN" == "true" ]]; then
  echo
  echo "==> 自动启动 xboard-nodes --mode ${AUTO_MODE}"
  if [[ -r /dev/tty ]]; then
    exec "$BIN_LINK" --mode "$AUTO_MODE" </dev/tty >/dev/tty 2>/dev/tty
  fi
  echo "未检测到可交互终端，跳过自动启动。"
fi
