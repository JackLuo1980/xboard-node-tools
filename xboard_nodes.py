#!/usr/bin/env python3
"""Interactive one-click entrypoint for xboard-node-tools."""

from __future__ import annotations

import argparse
import getpass
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROBE_SCRIPT = ROOT / "node_probe.py"
IMPORT_SCRIPT = ROOT / "xboard_import.py"


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


def choose_nodes_file(probe_output: str | None = None) -> str:
    if probe_output:
        candidate = Path(probe_output).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if candidate.exists():
            return str(candidate)

    candidates = find_nodes_candidates()
    if candidates:
        print("检测到以下节点 JSON 文件:")
        for index, path in enumerate(candidates, start=1):
            print(f"{index}. {path}")
        print()

        default = "1"
        choice = prompt_text("选择文件编号或直接输入路径", default)
        if choice.isdigit():
            selected_index = int(choice) - 1
            if 0 <= selected_index < len(candidates):
                return str(candidates[selected_index])
        if choice:
            return choice

    return prompt_text("节点 JSON 文件路径")


def run_probe_flow() -> tuple[int, str | None]:
    default_output = f"{socket.gethostname()}.nodes.json"
    output_path = prompt_text("导出文件名", default_output)
    host_override = prompt_text("手工指定导出地址(留空自动识别)", "")
    non_interactive = prompt_yes_no("是否非交互自动导出全部节点", False)

    command = [sys.executable, str(PROBE_SCRIPT), "-o", output_path]
    if host_override:
        command.extend(["--host", host_override])
    if non_interactive:
        command.append("--non-interactive")
    return run_command(command), output_path


def run_import_preview_and_apply(probe_output: str | None = None) -> int:
    input_path = choose_nodes_file(probe_output=probe_output)
    if not input_path:
        print("未提供 JSON 文件路径。", file=sys.stderr)
        return 1

    db_host = prompt_text("MySQL 主机", "127.0.0.1")
    db_port = prompt_text("MySQL 端口", "3306")
    db_name = prompt_text("数据库名", "xboard")
    db_user = prompt_text("数据库用户", "xboard")
    db_password = getpass.getpass("数据库密码: ").strip()
    groups = prompt_text("默认权限组(逗号分隔)", "vip1,vip2,vip3")
    force_insert = prompt_yes_no("是否强制插入，不做查重更新", False)

    base_command = [
        sys.executable,
        str(IMPORT_SCRIPT),
        input_path,
        "--db-host",
        db_host,
        "--db-port",
        db_port,
        "--db-name",
        db_name,
        "--db-user",
        db_user,
        "--db-password",
        db_password,
        "--groups",
        groups,
    ]
    if force_insert:
        base_command.append("--force-insert")

    preview_code = run_command(base_command)
    if preview_code != 0:
        return preview_code

    if not prompt_yes_no("确认将以上计划正式写入 Xboard", False):
        print("已取消写入。")
        return 0

    apply_command = list(base_command)
    apply_command.append("--apply")
    return run_command(apply_command)


def interactive_menu() -> int:
    print("xboard-node-tools 一键入口")
    print("1. 采集本机节点并导出 JSON")
    print("2. 导入 JSON 到 Xboard")
    print("3. 退出")
    print()

    choice = prompt_text("请选择", "1")
    if choice == "1":
        probe_code, probe_output = run_probe_flow()
        if probe_code != 0:
            return probe_code
        if prompt_yes_no("采集完成，是否现在继续导入到 Xboard", False):
            return run_import_preview_and_apply(probe_output=probe_output)
        return 0
    if choice == "2":
        return run_import_preview_and_apply()
    if choice == "3":
        return 0

    print("无效选项。", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-click interactive menu for xboard-node-tools.")
    parser.add_argument(
        "--mode",
        choices=["menu", "probe", "import"],
        default="menu",
        help="Run a specific flow directly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "probe":
        probe_code, _ = run_probe_flow()
        return probe_code
    if args.mode == "import":
        return run_import_preview_and_apply()
    return interactive_menu()


if __name__ == "__main__":
    raise SystemExit(main())
