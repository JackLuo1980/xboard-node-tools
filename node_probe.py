#!/usr/bin/env python3
"""Probe a server locally and export candidate Xboard nodes as JSON.

Designed for the user's preferred workflow:
1. Login to each server manually.
2. Run this script on that server.
3. Confirm each existing x-ui / 3x-ui inbound interactively, or create new nodes.
4. Copy the generated JSON to the Xboard server.
5. Import with `xboard_import.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_NAME = "xboard-node-export.json"
DEFAULT_GROUP_NAMES = ["vip1", "vip2", "vip3"]
REALITY_DEST_CANDIDATES = [
    "www.amazon.com",
    "www.apple.com",
    "www.cloudflare.com",
    "www.microsoft.com",
    "www.oracle.com",
    "www.paypal.com",
    "www.speedtest.net",
    "www.tesla.com",
]
PANEL_DB_CANDIDATES = [
    ("/etc/x-ui/x-ui.db", "x-ui"),
    ("/etc/3x-ui/x-ui.db", "3x-ui"),
    ("/usr/local/x-ui/x-ui.db", "x-ui"),
    ("/usr/local/3x-ui/x-ui.db", "3x-ui"),
]


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def prompt_text(message: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{message}{suffix}: ").strip()
    if raw:
        return raw
    return default or ""


def prompt_yes_no(message: str, default: bool = True) -> bool:
    default_hint = "Y/n" if default else "y/N"
    raw = input(f"{message} [{default_hint}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true"}


def prompt_int(message: str, default: int | None = None) -> int:
    while True:
        value = prompt_text(message, str(default) if default is not None else None)
        try:
            return int(value)
        except ValueError:
            print("请输入有效整数。", file=sys.stderr)


def normalize_protocol(protocol: str) -> str:
    value = (protocol or "").strip().lower()
    aliases = {
        "hy2": "hysteria2",
        "hysteria": "hysteria2",
        "ss": "shadowsocks",
    }
    return aliases.get(value, value)


def choose_host(override: str | None) -> str:
    if override:
        return override

    candidates: list[str] = []

    try:
        output = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        candidates.extend(output.split())
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            candidates.append(sock.getsockname()[0])
    except OSError:
        pass

    for candidate in candidates:
        if candidate and not candidate.startswith("127."):
            return candidate
    return socket.gethostname()


def find_existing_panel_db() -> tuple[Path | None, str | None]:
    for path_str, panel_name in PANEL_DB_CANDIDATES:
        path = Path(path_str)
        if path.exists():
            return path, panel_name
    return None, None


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def load_inbounds(db_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "inbounds"):
            return []
        columns = get_table_columns(conn, "inbounds")
        select_fields = [
            "id",
            "remark",
            "enable",
            "listen",
            "port",
            "protocol",
            "settings",
        ]
        optional_fields = [
            "up",
            "down",
            "total",
            "expiry_time",
            "stream_settings",
            "streamSettings",
            "sniffing",
        ]
        for field in optional_fields:
            if field in columns:
                select_fields.append(field)
        rows = conn.execute(
            f"""
            SELECT
                {", ".join(select_fields)}
            FROM inbounds
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    parsed: list[dict[str, Any]] = []
    for row in rows:
        settings_raw = row["settings"] or "{}"
        row_map = dict(row)
        stream_raw = row_map.get("stream_settings") or row_map.get("streamSettings") or "{}"
        sniffing_raw = row_map.get("sniffing") or "{}"
        try:
            settings = json.loads(settings_raw)
        except json.JSONDecodeError:
            settings = {}
        try:
            stream_settings = json.loads(stream_raw)
        except json.JSONDecodeError:
            stream_settings = {}
        try:
            sniffing = json.loads(sniffing_raw)
        except json.JSONDecodeError:
            sniffing = {}

        clients = settings.get("clients") or []
        parsed.append(
            {
                "id": row["id"],
                "remark": row["remark"] or "",
                "enable": bool(row["enable"]),
                "port": row["port"],
                "protocol": normalize_protocol(row["protocol"] or ""),
                "listen": row["listen"] or "",
                "settings": settings,
                "stream_settings": stream_settings,
                "sniffing": sniffing,
                "client_count": len(clients),
            }
        )
    return parsed


def reality_keypair_from_local_tools() -> tuple[str, str]:
    for binary in ("xray", "XrayR", "xrayr"):
        if not shutil.which(binary):
            continue
        try:
            result = subprocess.run(
                [binary, "x25519"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        if result.returncode != 0:
            continue
        private_key = ""
        public_key = ""
        for line in result.stdout.splitlines():
            lower = line.lower()
            if "private key" in lower:
                private_key = line.split(":", 1)[-1].strip()
            if "public key" in lower:
                public_key = line.split(":", 1)[-1].strip()
        if private_key and public_key:
            return private_key, public_key
    return "", ""


def build_network_settings_from_inbound(
    protocol: str,
    stream_settings: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    network = (stream_settings.get("network") or "tcp").lower()
    security = (stream_settings.get("security") or "").lower()
    result: dict[str, Any] = {
        "network": network,
        "security": security,
    }

    if protocol == "shadowsocks":
        result["method"] = settings.get("method") or "aes-256-gcm"

    if protocol in {"vless", "vmess"}:
        clients = settings.get("clients") or []
        if clients:
            client = clients[0]
            result["uuid"] = client.get("id") or ""
            result["flow"] = client.get("flow") or ""
            result["email"] = client.get("email") or ""

    if protocol == "trojan":
        clients = settings.get("clients") or []
        if clients:
            client = clients[0]
            result["password"] = client.get("password") or client.get("id") or ""
            result["email"] = client.get("email") or ""

    if protocol == "hysteria2":
        result["password"] = settings.get("auth") or settings.get("password") or ""

    if security == "reality":
        reality = stream_settings.get("realitySettings") or {}
        server_names = reality.get("serverNames") or []
        short_ids = reality.get("shortIds") or []
        result.update(
            {
                "reality_dest": reality.get("dest") or "",
                "reality_server_name": server_names[0] if server_names else "",
                "reality_private_key": reality.get("privateKey") or "",
                "reality_public_key": reality.get("publicKey") or "",
                "reality_short_id": short_ids[0] if short_ids else "",
            }
        )
    return result


def inbound_to_candidate(inbound: dict[str, Any], host: str) -> dict[str, Any]:
    protocol = normalize_protocol(inbound["protocol"])
    port = int(inbound["port"])
    network_settings = build_network_settings_from_inbound(
        protocol=protocol,
        stream_settings=inbound["stream_settings"],
        settings=inbound["settings"],
    )
    name = inbound["remark"] or f"{socket.gethostname()}-{protocol}-{port}"
    tags = ["imported"]
    if "3x" in (inbound.get("panel_name") or ""):
        tags.append("3x-ui")
    else:
        tags.append("x-ui")
    return {
        "selected": True,
        "name": name,
        "protocol": protocol,
        "type": protocol,
        "host": host,
        "listen_port": port,
        "server_port": port,
        "network": network_settings.get("network") or "tcp",
        "network_settings": network_settings,
        "show": True,
        "status": 1,
        "rate": "1",
        "sort": 0,
        "group_names": list(DEFAULT_GROUP_NAMES),
        "route_names": [],
        "tags": tags,
        "source": {
            "kind": "panel-inbound",
            "inbound_id": inbound["id"],
            "enabled": inbound["enable"],
            "client_count": inbound["client_count"],
        },
    }


def create_manual_candidate(host: str) -> dict[str, Any]:
    protocol = normalize_protocol(
        prompt_text(
            "节点类型 (vless/vmess/trojan/shadowsocks/hysteria2)",
            "vless",
        )
    )
    port = prompt_int("监听端口", 443)
    server_port = prompt_int("面板展示端口/NAT外部端口", port)
    name = prompt_text("节点名称", f"{socket.gethostname()}-{protocol}-{server_port}")
    network = prompt_text("传输层网络", "tcp").lower()

    network_settings: dict[str, Any] = {
        "network": network,
        "security": "",
    }

    if protocol in {"vless", "vmess"}:
        network_settings["uuid"] = str(uuid.uuid4())
        if protocol == "vless":
            network_settings["flow"] = "xtls-rprx-vision"
            if prompt_yes_no("是否启用 Reality", True):
                network_settings["security"] = "reality"
                reality_dest = secrets.choice(REALITY_DEST_CANDIDATES)
                network_settings["reality_server_name"] = prompt_text(
                    "Reality 域名",
                    reality_dest,
                )
                network_settings["reality_dest"] = prompt_text(
                    "Reality 目标",
                    f"{network_settings['reality_server_name']}:443",
                )
                private_key, public_key = reality_keypair_from_local_tools()
                network_settings["reality_private_key"] = private_key
                network_settings["reality_public_key"] = public_key
                network_settings["reality_short_id"] = secrets.token_hex(4)
        else:
            network_settings["alter_id"] = 0

    if protocol == "trojan":
        network_settings["password"] = secrets.token_urlsafe(16)

    if protocol == "shadowsocks":
        network_settings["method"] = prompt_text("加密方法", "aes-256-gcm")
        network_settings["password"] = secrets.token_urlsafe(16)

    if protocol == "hysteria2":
        network_settings["password"] = secrets.token_urlsafe(16)

    return {
        "selected": True,
        "name": name,
        "protocol": protocol,
        "type": protocol,
        "host": host,
        "listen_port": port,
        "server_port": server_port,
        "network": network,
        "network_settings": network_settings,
        "show": True,
        "status": 1,
        "rate": "1",
        "sort": 0,
        "group_names": list(DEFAULT_GROUP_NAMES),
        "route_names": [],
        "tags": ["manual-created"],
        "source": {
            "kind": "manual",
        },
    }


def choose_candidates_from_inbounds(
    inbounds: list[dict[str, Any]],
    host: str,
    panel_name: str,
) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for inbound in inbounds:
        inbound["panel_name"] = panel_name
        candidate = inbound_to_candidate(inbound, host)
        network_settings = candidate["network_settings"]
        print()
        print(f"发现入站: {candidate['name']}")
        print(f"  类型: {candidate['protocol']}")
        print(f"  端口: {candidate['server_port']}")
        print(f"  网络: {candidate['network']}")
        if network_settings.get("security") == "reality":
            print(f"  Reality: {network_settings.get('reality_server_name') or network_settings.get('reality_dest')}")
        if prompt_yes_no("导出这条节点", True):
            candidate["name"] = prompt_text("节点名称", candidate["name"])
            candidate["server_port"] = prompt_int("Xboard 展示端口", candidate["server_port"])
            candidate["host"] = prompt_text("节点地址", candidate["host"])
            candidate["group_names"] = [
                item.strip()
                for item in prompt_text("权限组(逗号分隔)", ",".join(DEFAULT_GROUP_NAMES)).split(",")
                if item.strip()
            ]
            chosen.append(candidate)
    return chosen


def build_export_payload(
    output_path: Path,
    host: str,
    panel_name: str | None,
    db_path: Path | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "generated_by": "scripts/node_probe.py",
        "server": {
            "hostname": socket.gethostname(),
            "host": host,
            "panel_name": panel_name or "",
            "panel_db_path": str(db_path) if db_path else "",
        },
        "defaults": {
            "group_names": list(DEFAULT_GROUP_NAMES),
        },
        "nodes": candidates,
        "output_path": str(output_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe local x-ui/3x-ui config and export Xboard node JSON.")
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT_NAME,
        help="Path to the output JSON file.",
    )
    parser.add_argument(
        "--host",
        help="Override exported host/IP.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Export all detected inbounds without confirmation. If no inbounds are found, exit directly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    host = choose_host(args.host)

    db_path, panel_name = find_existing_panel_db()
    inbounds: list[dict[str, Any]] = []
    if db_path:
        inbounds = load_inbounds(db_path)

    candidates: list[dict[str, Any]] = []
    if inbounds:
        print(f"检测到 {panel_name}，数据库: {db_path}")
        if args.non_interactive:
            for inbound in inbounds:
                inbound["panel_name"] = panel_name
                candidates.append(inbound_to_candidate(inbound, host))
        else:
            candidates = choose_candidates_from_inbounds(inbounds, host, panel_name or "")
    else:
        print("未检测到可读取的 x-ui / 3x-ui 入站。")
        if args.non_interactive:
            print("非交互模式下直接退出。", file=sys.stderr)
            return 1
        while prompt_yes_no("是否手工创建一条节点", True):
            candidates.append(create_manual_candidate(host))

    if not candidates:
        print("没有待导出的节点，已退出。", file=sys.stderr)
        return 1

    payload = build_export_payload(output_path, host, panel_name, db_path, candidates)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print()
    print(f"已导出 {len(candidates)} 条节点到: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
