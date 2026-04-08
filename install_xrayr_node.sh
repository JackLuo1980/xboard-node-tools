#!/usr/bin/env bash
set -euo pipefail

API_HOST="https://x.asli.eu.org"
API_KEY="umon3ErJKnqQbgB4aJAw"
NODE_ID_DEFAULT=""
CONFIG_PATH="/etc/XrayR/config.yml"
INSTALL_URL="https://raw.githubusercontent.com/XrayR-project/XrayR-release/master/install.sh"

log() {
  printf '%s\n' "$*"
}

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log "请使用 root 运行这个脚本。"
    exit 1
  fi
}

install_prereqs() {
  if command -v curl >/dev/null 2>&1 && command -v wget >/dev/null 2>&1 && command -v tar >/dev/null 2>&1; then
    return
  fi

  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y curl wget tar gzip ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y curl wget tar gzip ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    yum install -y curl wget tar gzip ca-certificates
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache curl wget tar gzip ca-certificates
  else
    log "未找到可用的包管理器，无法自动安装依赖。"
    exit 1
  fi
}

install_xrayr() {
  log "==> 安装 XrayR"
  curl -fsSL "$INSTALL_URL" | bash
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
  install_prereqs

  log "XrayR 一键安装脚本"
  log "ApiHost: ${API_HOST}"
  log "ApiKey : ${API_KEY}"
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

  install_xrayr
  write_config "$node_id"

  log "==> 重启 XrayR"
  systemctl enable XrayR >/dev/null 2>&1 || true
  systemctl restart XrayR

  log "==> 当前状态"
  systemctl status XrayR --no-pager || true
  log "==> 端口监听"
  ss -lntp | grep -E ':23221|XrayR' || true
  log "完成。"
}

main "$@"
