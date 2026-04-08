#!/usr/bin/env python3
"""Generate XrayR config templates from xboard_import result JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate XrayR config YAML from import result JSON.")
    parser.add_argument("input", help="Path to JSON written by xboard_import.py --result-output")
    parser.add_argument("--panel-host", required=True, help="Xboard panel URL, e.g. https://x.asli.eu.org")
    parser.add_argument("--api-key", required=True, help="XrayR API key / panel key")
    parser.add_argument(
        "--output",
        help="Optional directory to write per-node YAML files. Defaults to printing all templates.",
    )
    parser.add_argument(
        "--update-periodic",
        default="60",
        help="XrayR UpdatePeriodic value, default 60.",
    )
    parser.add_argument(
        "--cert-mode",
        default="none",
        help="CertMode to place in the template, default none.",
    )
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def node_type_for_xrayr(node: dict[str, Any]) -> str:
    node_type = str(node.get("type") or "").lower()
    mapping = {
        "vless": "V2ray",
        "vmess": "V2ray",
        "trojan": "Trojan",
        "shadowsocks": "Shadowsocks",
        "hysteria2": "Hysteria2",
    }
    return mapping.get(node_type, "V2ray")


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def build_yaml(node: dict[str, Any], panel_host: str, api_key: str, update_periodic: str, cert_mode: str) -> str:
    network_settings = node.get("network_settings") or {}
    source = node.get("source") or {}
    node_type = node_type_for_xrayr(node)
    enable_vless = str(node.get("type") or "").lower() == "vless"
    enable_xtls = network_settings.get("security") == "reality"
    fallback_note = ""
    original_port = source.get("original_port")
    if original_port:
        fallback_note = f"# 原 x-ui 端口: {original_port}\n"

    lines = [
        "Log:",
        "  Level: warning",
        '  AccessPath: ""',
        '  ErrorPath: ""',
        "DnsConfigPath: null",
        "RouteConfigPath: null",
        "InboundConfigPath: null",
        "OutboundConfigPath: null",
        "ConnetionConfig:",
        "  Handshake: 4",
        "  ConnIdle: 30",
        "  UplinkOnly: 2",
        "  DownlinkOnly: 4",
        "  BufferSize: 64",
        "Nodes:",
        "  - PanelType: V2board",
        "    ApiConfig:",
        f"      ApiHost: {panel_host}",
        f"      ApiKey: {api_key}",
        f"      NodeID: {node.get('node_id')}",
        f"      NodeType: {node_type}",
        "      Timeout: 30",
        f"      EnableVless: {bool_text(enable_vless)}",
        f"      EnableXTLS: {bool_text(enable_xtls)}",
        "      SpeedLimit: 0",
        "      DeviceLimit: 0",
        "      RuleListPath: /etc/XrayR/rulelist",
        "      DisableCustomConfig: false",
        "    ControllerConfig:",
        "      ListenIP: 0.0.0.0",
        "      SendIP: 0.0.0.0",
        f"      UpdatePeriodic: {update_periodic}",
        "      EnableDNS: false",
        "      DNSType: AsIs",
        "      EnableProxyProtocol: false",
        "      AutoSpeedLimitConfig:",
        "        Limit: 0",
        "        WarnTimes: 0",
        "        LimitSpeed: 0",
        "        LimitDuration: 0",
        "      GlobalDeviceLimitConfig:",
        "        Enable: false",
        "        RedisAddr: 127.0.0.1:6379",
        "        RedisPassword: null",
        "        RedisDB: 0",
        "        Timeout: 5",
        "        Expiry: 60",
        "      CertConfig:",
        f"        CertMode: {cert_mode}",
        '        CertDomain: ""',
        '        CertFile: ""',
        '        KeyFile: ""',
        '        Provider: ""',
        '        Email: ""',
    ]
    return f"# 节点名称: {node.get('name')}\n{fallback_note}" + "\n".join(lines) + "\n"


def slugify(text: str) -> str:
    clean = []
    for char in text.lower():
        if char.isalnum():
            clean.append(char)
        elif char in {" ", "-", "_"}:
            clean.append("-")
    slug = "".join(clean).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "node"


def main() -> int:
    args = parse_args()
    payload = load_json(args.input)
    nodes = payload.get("nodes") or []
    if not nodes:
        raise SystemExit("结果 JSON 中没有节点。")

    output_dir = None
    if args.output:
        output_dir = Path(args.output).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    for index, node in enumerate(nodes, start=1):
        yaml_text = build_yaml(
            node=node,
            panel_host=args.panel_host,
            api_key=args.api_key,
            update_periodic=str(args.update_periodic),
            cert_mode=args.cert_mode,
        )
        if output_dir:
            filename = f"{index:02d}-{slugify(str(node.get('name') or 'node'))}.yml"
            path = output_dir / filename
            path.write_text(yaml_text, encoding="utf-8")
            print(f"已生成: {path}")
        else:
            if index > 1:
                print("---")
            print(yaml_text.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
