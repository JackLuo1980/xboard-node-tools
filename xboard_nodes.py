#!/usr/bin/env python3
"""Interactive one-click entrypoint for xboard-node-tools."""

from __future__ import annotations

import argparse
import getpass
import json
import shlex
import shutil
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
PROFILE_REQUIRED_FIELDS = [
    "ssh_host",
    "ssh_user",
    "remote_json_dir",
    "db_host",
    "db_port",
    "db_name",
    "db_user",
    "db_password",
    "groups",
]

TTY_STREAM = None
try:
    TTY_STREAM = open("/dev/tty", "r+", encoding="utf-8", buffering=1)
except OSError:
    TTY_STREAM = None


def tty_print(message: str = "") -> None:
    stream = TTY_STREAM or sys.stdout
    print(message, file=stream, flush=True)


def tty_prompt(message: str) -> str:
    stream = TTY_STREAM or sys.stdout
    stream.write(message)
    stream.flush()
    input_stream = TTY_STREAM or sys.stdin
    raw = input_stream.readline()
    if raw == "":
        raise EOFError("EOF when reading a line")
    return raw.rstrip("\n")


def prompt_text(message: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = tty_prompt(f"{message}{suffix}: ").strip()
    if raw:
        return raw
    return default or ""


def prompt_yes_no(message: str, default: bool = True) -> bool:
    default_hint = "Y/n" if default else "y/N"
    raw = tty_prompt(f"{message} [{default_hint}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true"}


def run_command(args: list[str]) -> int:
    tty_print()
    tty_print("执行命令:")
    tty_print(" ".join(args))
    tty_print()
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


def profile_complete(profile: dict[str, Any]) -> bool:
    return all(str(profile.get(field) or "").strip() for field in PROFILE_REQUIRED_FIELDS)


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
            tty_print(f"自动选中节点 JSON: {candidates[0]}")
            return str(candidates[0])

        tty_print("检测到以下节点 JSON 文件:")
        for index, path in enumerate(candidates, start=1):
            tty_print(f"{index}. {path}")
        tty_print()
        choice = prompt_text("选择文件编号或直接输入路径", "1")
        if choice.isdigit():
            selected_index = int(choice) - 1
            if 0 <= selected_index < len(candidates):
                return str(candidates[selected_index])
        if choice:
            return choice

    return prompt_text("节点 JSON 文件路径")


def load_nodes_payload(path: str) -> dict[str, Any] | None:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def payload_contains_xui_draft(path: str) -> bool:
    payload = load_nodes_payload(path)
    if not payload:
        return False
    for node in payload.get("nodes") or []:
        source = node.get("source") or {}
        if source.get("kind") == "panel-inbound-clone":
            return True
        tags = node.get("tags") or []
        if any(tag in {"x-ui", "3x-ui"} for tag in tags):
            return True
    return False


def notify_xui_draft(path: str) -> None:
    tty_print("当前导出结果是 x-ui 迁移草稿，按当前规则不进入上传步骤。")
    tty_print("请把它作为本地草稿保留，后续若需要正式上线，再整理成可用后端节点。")


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


def run_probe_auto_flow() -> tuple[int, str | None]:
    output_path = f"{socket.gethostname()}.nodes.json"
    command = [sys.executable, str(PROBE_SCRIPT), "-o", output_path, "--non-interactive"]
    return run_command(command), output_path


def prompt_xboard_profile(config: dict[str, Any]) -> dict[str, Any]:
    profile = dict(config.get("default_xboard") or {})
    if profile_complete(profile):
        print(
            "使用默认 Xboard 配置: "
            f"{profile.get('ssh_user')}@{profile.get('ssh_host')} "
            f"/ DB {profile.get('db_name')}"
        )
        return profile

    profile["ssh_host"] = prompt_text("Xboard SSH 主机", profile.get("ssh_host") or "")
    profile["ssh_user"] = prompt_text("Xboard SSH 用户", profile.get("ssh_user") or "root")
    profile["ssh_password"] = profile.get("ssh_password") or ""
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


def maybe_save_profile(config: dict[str, Any], profile: dict[str, Any]) -> None:
    if config.get("default_xboard") == profile:
        return
    if prompt_yes_no("是否保存为默认 Xboard 配置，供下次直接使用", True):
        config["default_xboard"] = profile
        save_config(config)


def command_prefix_for_profile(profile: dict[str, Any]) -> list[str]:
    ssh_password = str(profile.get("ssh_password") or "").strip()
    if ssh_password:
        return ["sshpass", "-p", ssh_password]
    return []


def ssh_common_options() -> list[str]:
    return [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=15",
    ]


def ensure_sshpass_if_needed(profile: dict[str, Any]) -> None:
    if not str(profile.get("ssh_password") or "").strip():
        return
    if shutil.which("sshpass"):
        return

    tty_print("检测到预置 SSH 密码，但本机未安装 sshpass，尝试自动安装...")

    install_commands = [
        ["apt-get", "update", "-y"],
        ["apt-get", "install", "-y", "sshpass"],
    ]

    if shutil.which("apt-get"):
        for command in install_commands:
            result = subprocess.run(command, check=False)
            if result.returncode != 0:
                raise RuntimeError("自动安装 sshpass 失败，请手工安装后重试。")
        if shutil.which("sshpass"):
            return

    if shutil.which("dnf"):
        result = subprocess.run(["dnf", "install", "-y", "sshpass"], check=False)
        if result.returncode == 0 and shutil.which("sshpass"):
            return

    if shutil.which("yum"):
        subprocess.run(["yum", "install", "-y", "epel-release"], check=False)
        result = subprocess.run(["yum", "install", "-y", "sshpass"], check=False)
        if result.returncode == 0 and shutil.which("sshpass"):
            return

    if shutil.which("apk"):
        result = subprocess.run(["apk", "add", "--no-cache", "sshpass"], check=False)
        if result.returncode == 0 and shutil.which("sshpass"):
            return

    raise RuntimeError("已配置 SSH 密码，但当前机器未安装 sshpass，且自动安装失败。")


def build_ssh_command(profile: dict[str, Any], remote_command: str, tty: bool = False) -> list[str]:
    ssh_target = f"{profile['ssh_user']}@{profile['ssh_host']}"
    command = command_prefix_for_profile(profile) + ["ssh", *ssh_common_options()]
    if tty:
        command.append("-t")
    command.extend([ssh_target, f"bash -lc {shlex.quote(remote_command)}"])
    return command


def build_scp_command(profile: dict[str, Any], local_path: str, remote_path: str) -> list[str]:
    ssh_target = f"{profile['ssh_user']}@{profile['ssh_host']}"
    return command_prefix_for_profile(profile) + ["scp", *ssh_common_options(), local_path, f"{ssh_target}:{remote_path}"]


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

    if payload_contains_xui_draft(input_path):
        print("当前 JSON 包含 x-ui 迁移草稿，按当前规则不自动上传到 Xboard。", file=sys.stderr)
        print("请先把它作为本地草稿保留，或整理成真正的后端节点后再上传。", file=sys.stderr)
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

    maybe_save_profile(config, profile)
    ensure_sshpass_if_needed(profile)

    remote_json_path = f"{profile['remote_json_dir'].rstrip('/')}/{input_file.name}"

    tty_print("步骤 1/4: 远端安装或更新 xboard-node-tools")
    install_code = run_command(
        build_ssh_command(profile, f"curl -fsSL {shlex.quote(INSTALL_URL)} | AUTO_RUN=false bash")
    )
    if install_code != 0:
        tty_print("失败: 远端安装或更新 xboard-node-tools 未成功。")
        return install_code
    tty_print("成功: 远端工具已准备完成。")

    tty_print("步骤 2/4: 上传节点 JSON 到 Xboard 服务器")
    copy_code = run_command(build_scp_command(profile, str(input_file), remote_json_path))
    if copy_code != 0:
        tty_print("失败: 节点 JSON 上传未成功。")
        return copy_code
    tty_print("成功: 节点 JSON 已上传。")

    tty_print("步骤 3/4: 远端 dry-run 预览导入计划")
    preview_code = run_command(
        build_ssh_command(
            profile,
            build_remote_import_command(remote_json_path, profile, apply=False),
            tty=True,
        )
    )
    if preview_code != 0:
        tty_print("失败: dry-run 预览未成功。")
        return preview_code
    tty_print("成功: dry-run 已完成。")

    if not prompt_yes_no("确认将以上计划正式写入 Xboard", False):
        tty_print("已取消写入。")
        return 0

    tty_print("步骤 4/4: 正式写入 Xboard")
    apply_code = run_command(
        build_ssh_command(
            profile,
            build_remote_import_command(remote_json_path, profile, apply=True),
            tty=True,
        )
    )
    if apply_code != 0:
        tty_print("失败: 正式写入 Xboard 未成功。")
        return apply_code
    tty_print("成功: 节点已写入 Xboard。")
    return 0


def run_sync_flow() -> int:
    export_code, export_path = run_probe_auto_flow()
    if export_code != 0:
        return export_code
    return run_upload_flow(default_json=export_path)


def interactive_menu() -> int:
    tty_print("xboard-node-tools 一键入口")
    tty_print("1. 导出现有节点到 JSON")
    tty_print("2. 上传到 Xboard")
    tty_print("3. 创建新的节点 JSON")
    tty_print("4. 一键同步到 Xboard")
    tty_print("5. 退出")
    tty_print()

    choice = prompt_text("请选择", "1")
    if choice == "1":
        export_code, export_path = run_probe_flow(manual_only=False)
        if export_code != 0:
            return export_code
        if export_path and payload_contains_xui_draft(export_path):
            notify_xui_draft(export_path)
            return 0
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
        create_code, export_path = run_probe_flow(manual_only=False)
        if create_code != 0:
            return create_code
        if export_path and payload_contains_xui_draft(export_path):
            notify_xui_draft(export_path)
            return 0
        if prompt_yes_no("创建完成，是否现在上传到 Xboard", False):
            return run_upload_flow(default_json=export_path)
        return 0
    if choice == "4":
        return run_sync_flow()
    if choice == "5":
        return 0

    print("无效选项。", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-click interactive menu for xboard-node-tools.")
    parser.add_argument(
        "--mode",
        choices=["menu", "export", "upload", "create", "sync"],
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
        code, _ = run_probe_flow(manual_only=False)
        return code
    if args.mode == "sync":
        return run_sync_flow()
    return interactive_menu()


if __name__ == "__main__":
    raise SystemExit(main())
