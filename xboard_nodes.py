#!/usr/bin/env python3
"""Interactive one-click entrypoint for xboard-node-tools."""

from __future__ import annotations

import argparse
import getpass
import json
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROBE_SCRIPT = ROOT / "node_probe.py"
IMPORT_SCRIPT = ROOT / "xboard_import.py"
CONFIG_PATH = Path.home() / ".config" / "xboard-node-tools" / "config.json"
INSTALL_URL = "https://github.com/JackLuo1980/xboard-node-tools/raw/main/install.sh"


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


def run_command(args: list[str]) -> int:
    print()
    print("执行命令:")
    print(" ".join(args))
    print()
    result = subprocess.run(args, check=False)
    return result.returncode


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_nodes_candidates() -> list[Path]:
    search_dirs = []
    cwd = Path.cwd().resolve()
    if cwd not in search_dirs:
        search_dirs.append(cwd)
    if ROOT not in search_dirs:
        search_dirs.append(ROOT)

    seen: set[Path] = set()
    candidates: list[Path] = []
    for directory in search_dirs:
        for path in sorted(directory.glob("*.nodes.json")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(resolved)
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates


def choose_nodes_file(default_path: str | None = None) -> str:
    if default_path:
        candidate = Path(default_path).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if candidate.exists():
            return str(candidate)

    candidates = find_nodes_candidates()
    if candidates:
        if len(candidates) == 1:
            print(f"自动选中节点 JSON: {candidates[0]}")
            return str(candidates[0])

        print("检测到以下节点 JSON 文件:")
        for index, path in enumerate(candidates, start=1):
            print(f"{index}. {path}")
        print()
        choice = prompt_text("选择文件编号或直接输入路径", "1")
        if choice.isdigit():
            selected_index = int(choice) - 1
            if 0 <= selected_index < len(candidates):
                return str(candidates[selected_index])
        if choice:
            return choice

    return prompt_text("节点 JSON 文件路径")


def run_probe_flow(manual_only: bool = False) -> tuple[int, str | None]:
    default_output = f"{socket.gethostname()}.nodes.json"
    output_path = prompt_text("导出文件名", default_output)
    host_override = prompt_text("手工指定导出地址(留空自动识别)", "")
    non_interactive = False if manual_only else prompt_yes_no("是否非交互自动导出全部节点", False)

    command = [sys.executable, str(PROBE_SCRIPT), "-o", output_path]
    if manual_only:
        command.append("--manual-only")
    if host_override:
        command.extend(["--host", host_override])
    if non_interactive:
        command.append("--non-interactive")
    return run_command(command), output_path


def prompt_xboard_profile(config: dict[str, Any]) -> dict[str, Any]:
    profile = dict(config.get("default_xboard") or {})
    profile["ssh_host"] = prompt_text("Xboard SSH 主机", profile.get("ssh_host") or "")
    profile["ssh_user"] = prompt_text("Xboard SSH 用户", profile.get("ssh_user") or "root")
    profile["remote_json_dir"] = prompt_text("远端 JSON 目录", profile.get("remote_json_dir") or "/root")
    profile["db_host"] = prompt_text("MySQL 主机", profile.get("db_host") or "127.0.0.1")
    profile["db_port"] = prompt_text("MySQL 端口", str(profile.get("db_port") or "3306"))
    profile["db_name"] = prompt_text("数据库名", profile.get("db_name") or "xboard")
    profile["db_user"] = prompt_text("数据库用户", profile.get("db_user") or "xboard")
    saved_password = profile.get("db_password") or ""
    if saved_password and prompt_yes_no("是否继续使用已保存的数据库密码", True):
        db_password = saved_password
    else:
        db_password = getpass.getpass("数据库密码: ").strip()
    profile["db_password"] = db_password
    profile["groups"] = prompt_text("默认权限组(逗号分隔)", profile.get("groups") or "vip1,vip2,vip3")
    return profile


def build_remote_import_command(remote_json_path: str, profile: dict[str, Any], apply: bool) -> str:
    command = [
        "python3",
        "/opt/xboard-node-tools/xboard_import.py",
        remote_json_path,
        "--db-host",
        str(profile["db_host"]),
        "--db-port",
        str(profile["db_port"]),
        "--db-name",
        str(profile["db_name"]),
        "--db-user",
        str(profile["db_user"]),
        "--db-password",
        str(profile["db_password"]),
        "--groups",
        str(profile["groups"]),
    ]
    if apply:
        command.append("--apply")
    return " ".join(shlex.quote(item) for item in command)


def run_upload_flow(default_json: str | None = None) -> int:
    input_path = choose_nodes_file(default_json)
    if not input_path:
        print("未找到可上传的节点 JSON。", file=sys.stderr)
        return 1

    input_file = Path(input_path).expanduser()
    if not input_file.is_absolute():
        input_file = (Path.cwd() / input_file).resolve()
    if not input_file.exists():
        print(f"文件不存在: {input_file}", file=sys.stderr)
        return 1

    config = load_config()
    profile = prompt_xboard_profile(config)
    if not profile.get("ssh_host"):
        print("未提供 Xboard SSH 主机。", file=sys.stderr)
        return 1

    if prompt_yes_no("是否保存为默认 Xboard 配置，供下次直接使用", True):
        config["default_xboard"] = profile
        save_config(config)

    ssh_target = f"{profile['ssh_user']}@{profile['ssh_host']}"
    remote_json_path = f"{profile['remote_json_dir'].rstrip('/')}/{input_file.name}"

    install_code = run_command(
        [
            "ssh",
            ssh_target,
            f"curl -fsSL {shlex.quote(INSTALL_URL)} | bash",
        ]
    )
    if install_code != 0:
        return install_code

    copy_code = run_command(
        [
            "scp",
            str(input_file),
            f"{ssh_target}:{remote_json_path}",
        ]
    )
    if copy_code != 0:
        return copy_code

    preview_code = run_command(
        [
            "ssh",
            "-t",
            ssh_target,
            build_remote_import_command(remote_json_path, profile, apply=False),
        ]
    )
    if preview_code != 0:
        return preview_code

    if not prompt_yes_no("确认将以上计划正式写入 Xboard", False):
        print("已取消写入。")
        return 0

    return run_command(
        [
            "ssh",
            "-t",
            ssh_target,
            build_remote_import_command(remote_json_path, profile, apply=True),
        ]
    )


def interactive_menu() -> int:
    print("xboard-node-tools 一键入口")
    print("1. 导出现有节点到 JSON")
    print("2. 上传到 Xboard")
    print("3. 创建新的节点 JSON")
    print("4. 退出")
    print()

    choice = prompt_text("请选择", "1")
    if choice == "1":
        export_code, export_path = run_probe_flow(manual_only=False)
        if export_code != 0:
            return export_code
        if prompt_yes_no("导出完成，是否现在上传到 Xboard", False):
            return run_upload_flow(default_json=export_path)
        return 0
    if choice == "2":
        candidates = find_nodes_candidates()
        if not candidates and prompt_yes_no("当前未发现节点 JSON，是否先导出", True):
            export_code, export_path = run_probe_flow(manual_only=False)
            if export_code != 0:
                return export_code
            return run_upload_flow(default_json=export_path)
        return run_upload_flow()
    if choice == "3":
        create_code, export_path = run_probe_flow(manual_only=True)
        if create_code != 0:
            return create_code
        if prompt_yes_no("创建完成，是否现在上传到 Xboard", False):
            return run_upload_flow(default_json=export_path)
        return 0
    if choice == "4":
        return 0

    print("无效选项。", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-click interactive menu for xboard-node-tools.")
    parser.add_argument(
        "--mode",
        choices=["menu", "export", "upload", "create"],
        default="menu",
        help="Run a specific flow directly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "export":
        code, _ = run_probe_flow(manual_only=False)
        return code
    if args.mode == "upload":
        return run_upload_flow()
    if args.mode == "create":
        code, _ = run_probe_flow(manual_only=True)
        return code
    return interactive_menu()


if __name__ == "__main__":
    raise SystemExit(main())
