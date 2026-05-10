#!/usr/bin/env python3
"""release-cli 版本 Hook 示例脚本。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HookContext:
    """Hook 上下文。"""

    version: str
    previous_version: str
    version_source: str
    project_root: Path
    config_file: Path
    version_file: Path
    git_tag: str


def load_context(payload_path: Path) -> HookContext:
    """从 release-cli 生成的 payload 中读取上下文。"""
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    return HookContext(
        version=payload["version"],
        previous_version=payload["previous_version"],
        version_source=payload["version_source"],
        project_root=Path(payload["project_root"]),
        config_file=Path(payload["config_file"]),
        version_file=Path(payload["version_file"]),
        git_tag=payload["git_tag"],
    )


def write_json_version(file_path: Path, version: str, key: str = "version") -> None:
    """把版本号写入 JSON 文件。"""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    data[key] = version
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(file_path: Path, content: str) -> None:
    """写入纯文本文件。"""
    file_path.write_text(content, encoding="utf-8")


def apply_version_update(context: HookContext) -> None:
    """只需要在这里补你的业务逻辑。"""
    # 默认先同步 VERSION，保证 file / git-tag 两种模式下产物里的版本文件一致。
    write_text(context.version_file, f"v{context.version}\n")

    # 示例 1：同步 package.json
    # package_json = context.project_root / "package.json"
    # if package_json.exists():
    #     write_json_version(package_json, context.version)

    # 示例 2：同步自定义纯文本版本文件
    # custom_version = context.project_root / "apps/web/VERSION"
    # if custom_version.exists():
    #     write_text(custom_version, f"{context.version}\n")

    # 示例 3：根据版本来源做不同处理
    # if context.version_source == "git-tag":
    #     print(f"tag will be {context.git_tag}")

    pass


def main() -> None:
    """读取 payload 并执行 Hook。"""
    if len(sys.argv) != 2:
        raise SystemExit("usage: release-version-hook.py <payload.json>")

    payload_path = Path(sys.argv[1]).resolve()
    context = load_context(payload_path)
    apply_version_update(context)
    print(f"hook completed for {context.version}")


if __name__ == "__main__":
    main()
