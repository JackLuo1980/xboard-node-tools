#!/usr/bin/env bash
set -euo pipefail

API_HOST="https://x.asli.eu.org"
API_KEY="umon3ErJKnqQbgB4aJAw"
NODE_ID_DEFAULT=""
CONFIG_PATH="/etc/XrayR/config.yml"
REPO_API_URL="https://api.github.com/repos/XrayR-project/XrayR/releases/latest"
RELEASE_BASE_URL="https://github.com/XrayR-project/XrayR/releases/download"
MIRROR_BASE_URL="https://ghproxy.com/https://github.com/XrayR-project/XrayR/releases/download"
SERVICE_PATH="/etc/systemd/system/XrayR.service"
INSTALL_DIR="/usr/local/XrayR"

log() {
  printf '%s\n' "$*"
}

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log "请使用 root 运行这个脚本。"
    exit 1
  fi
}

ensure_tools() {
  local missing=()

  command -v curl >/dev/null 2>&1 || missing+=("curl")
  command -v unzip >/dev/null 2>&1 || missing+=("unzip")

  if [[ "${#missing[@]}" -ne 0 ]]; then
    log "缺少必要工具: ${missing[*]}"
    log "请先安装 curl 和 unzip，再重新运行脚本。"
    exit 1
  fi
}

download_latest_version() {
  local tag
  tag="$(curl -fsSL "$REPO_API_URL" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  if [[ -z "$tag" ]]; then
    log "无法获取 XrayR 最新版本号"
    exit 1
  fi
  printf '%s\n' "$tag"
}

extract_zip() {
  local zip_path="$1"
  unzip -oq "$zip_path" -d "$INSTALL_DIR"
}

install_xrayr() {
  local version="$1"
  local arch="$2"
  local zip_path="${INSTALL_DIR}/XrayR-linux.zip"
  local primary_url="${RELEASE_BASE_URL}/${version}/XrayR-linux-${arch}.zip"
  local mirror_url="${MIRROR_BASE_URL}/${version}/XrayR-linux-${arch}.zip"
  local candidates=()
  if [[ -n "${XRAYR_DOWNLOAD_URL:-}" ]]; then
    candidates+=("${XRAYR_DOWNLOAD_URL}")
  fi
  candidates+=("$mirror_url" "$primary_url")
  local speed_time="${XRAYR_DOWNLOAD_SPEED_TIME:-20}"
  local speed_limit="${XRAYR_DOWNLOAD_SPEED_LIMIT:-32768}"

  log "==> 安装 XrayR"
  log "版本: ${version}"
  log "架构: ${arch}"

  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"

  local success=0
  for url in "${candidates[@]}"; do
    rm -f "$zip_path"
    log "==> 下载: $url"
    if curl -fL --retry 3 --retry-all-errors --connect-timeout 15 --speed-time "$speed_time" --speed-limit "$speed_limit" --max-time 1200 -o "$zip_path" "$url"; then
      if unzip -t "$zip_path" >/dev/null 2>&1; then
        success=1
        break
      fi
      log "下载包校验失败，准备重试下一来源。"
    else
      log "下载失败，准备重试下一来源。"
    fi
  done

  if [[ "$success" -ne 1 ]]; then
    log "XrayR 下载失败：所有来源都不可用。"
    exit 1
  fi

  extract_zip "$zip_path"
  rm -f "$zip_path"

  if [[ ! -x "${INSTALL_DIR}/XrayR" ]]; then
    chmod +x "${INSTALL_DIR}/XrayR"
  fi

  cat >"$SERVICE_PATH" <<EOF
[Unit]
Description=XrayR Service
After=network.target nss-lookup.target

[Service]
Type=simple
User=root
LimitNOFILE=1048576
ExecStart=${INSTALL_DIR}/XrayR --config /etc/XrayR/config.yml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable XrayR >/dev/null 2>&1 || true
}

write_config() {
  local node_id="$1"
  mkdir -p /etc/XrayR

  if [[ -f "$CONFIG_PATH" ]]; then
    cp "$CONFIG_PATH" "${CONFIG_PATH}.bak.$(date +%Y%m%d%H%M%S)"
    log "==> 已备份旧配置到 ${CONFIG_PATH}.bak.*"
  fi

  cat >"$CONFIG_PATH" <<EOF
Log:
  Level: warning
  AccessPath: ""
  ErrorPath: ""

DnsConfigPath: null
RouteConfigPath: null
InboundConfigPath: null
OutboundConfigPath: null

ConnectionConfig:
  Handshake: 5
  ConnIdle: 15
  UplinkOnly: 5
  DownlinkOnly: 5
  BufferSize: 256

Nodes:
  - PanelType: "NewV2board"
    ApiConfig:
      ApiHost: "${API_HOST}"
      ApiKey: "${API_KEY}"
      NodeID: ${node_id}
      NodeType: "V2ray"
      Timeout: 30
      EnableVless: true
      EnableXTLS: true
      VlessFlow: "xtls-rprx-vision"
      SpeedLimit: 0
      DeviceLimit: 0
      RuleListPath: ""
      DisableCustomConfig: false
    ControllerConfig:
      ListenIP: "0.0.0.0"
      SendIP: "0.0.0.0"
      UpdatePeriodic: 5
      EnableDNS: true
      DNSType: UseIPv4
      DisableUploadTraffic: false
      DisableGetRule: false
      DisableIVCheck: false
      DisableSniffing: false
      EnableProxyProtocol: false
      DisableLocalREALITYConfig: true
      REALITYConfigs:
        Show: true
      AutoSpeedLimitConfig:
        Limit: 0
        WarnTimes: 0
        LimitSpeed: 0
        LimitDuration: 0
      GlobalDeviceLimitConfig:
        Enable: false
        RedisAddr: 127.0.0.1:6379
        RedisPassword: ""
        RedisDB: 0
        Timeout: 5
        Expiry: 60
      EnableFallback: false
      FallBackConfigs: []
      CertConfig:
        CertMode: none
        RejectUnknownSni: false
        CertDomain: ""
        CertFile: ""
        KeyFile: ""
        Provider: ""
        Email: ""
        DNSEnv: []
EOF
}

main() {
  need_root
  ensure_tools

  log "XrayR 一键安装脚本"
  log "ApiHost: ${API_HOST}"
  log "ApiKey : ${API_KEY}"

  local input_node_id=""
  if [[ -r /dev/tty ]]; then
    printf '请输入 NodeID: ' >/dev/tty
    read -r input_node_id </dev/tty
  else
    printf '请输入 NodeID: '
    read -r input_node_id
  fi

  local node_id="${input_node_id:-}"
  if [[ -z "$node_id" ]]; then
    log "NodeID 为必填项，不能为空。"
    exit 1
  fi

  local version
  version="$(download_latest_version)"
  local arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64|x64) arch="64" ;;
    aarch64|arm64) arch="arm64-v8a" ;;
    s390x) arch="s390x" ;;
    *) arch="64" ;;
  esac

  install_xrayr "$version" "$arch"
  write_config "$node_id"

  log "==> 重启 XrayR"
  systemctl restart XrayR

  log "==> 当前状态"
  systemctl status XrayR --no-pager || true
  log "==> 端口监听"
  ss -lntp | grep -E ':23221|XrayR' || true
  log "完成。"
}

main "$@"
