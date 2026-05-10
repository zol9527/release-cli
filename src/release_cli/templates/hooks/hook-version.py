#!/usr/bin/env python3
"""release-cli version hook 模板。

触发时机:
    `release-cli version <value> --write` 写入版本文件之后自动执行。

默认行为:
    只同步 release-cli 自己的版本状态文件，不假设任何业务技术栈。

如何扩展:
    在下面的 `sync_package_json()`、`sync_custom_files()` 等函数中补充你的
    项目逻辑。模板不会默认修改 package.json、构建元数据或其他业务文件。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HookContext:
    """release-cli 传入的 version hook 上下文。"""

    version: str
    previous_version: str
    version_source: str
    project_root: Path
    config_file: Path | None
    version_file: Path | None
    git_tag: str


def load_context(payload_path: Path) -> HookContext:
    """从 release-cli 生成的 payload.json 读取上下文。"""
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    return HookContext(
        version=payload["version"],
        previous_version=payload.get("previous_version", ""),
        version_source=payload.get("version_source", ""),
        project_root=Path(payload["project_root"]),
        config_file=Path(payload["config_file"]) if payload.get("config_file") else None,
        version_file=Path(payload["version_file"]) if payload.get("version_file") else None,
        git_tag=payload.get("git_tag", ""),
    )


def write_text(file_path: Path, content: str) -> None:
    """写入纯文本文件，并确保父目录存在。"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def write_json_version(file_path: Path, version: str, key: str = "version") -> None:
    """把 JSON 文件中的版本字段更新为指定版本。"""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    data[key] = version
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# -----------------------------------------------------------------------------
# 生命周期 hook
# -----------------------------------------------------------------------------


def before_all(ctx: HookContext) -> None:
    """全部版本同步开始前。

    适合放置轻量校验，例如确认项目根目录、检查必需文件是否存在。
    """
    pass


def sync_version_file(ctx: HookContext) -> None:
    """同步 release-cli 自己的版本状态文件。

    通常不需要修改。`ctx.version_file` 来自 `.release/*.yml` 的
    `version.file` 字段。
    """
    if ctx.version_file is None:
        return
    write_text(ctx.version_file, f"v{ctx.version}\n")
    print(f"✅ 已同步 VERSION: {ctx.version_file}")


def sync_package_json(ctx: HookContext) -> None:
    """按需同步 package.json。

    默认不启用，避免假设项目一定是 Node/Bun/npm 项目。
    如果需要，取消下面示例代码的注释即可。
    """
    # package_json = ctx.project_root / "package.json"
    # if not package_json.exists():
    #     return
    # write_json_version(package_json, ctx.version)
    # print(f"✅ 已同步 package.json: {package_json}")
    pass


def sync_custom_files(ctx: HookContext) -> None:
    """按需同步项目自己的版本文件。

    你可以在这里补充任何项目专属逻辑，例如:
    - 写入前端展示用 version.ts
    - 同步后端 build metadata
    - 生成 release info JSON
    - 更新其他 workspace 内部的版本声明文件
    """
    # 示例：写入一个自定义 JSON 文件
    # release_info = ctx.project_root / "release-info.json"
    # release_info.write_text(
    #     json.dumps({"version": ctx.version, "tag": ctx.git_tag}, ensure_ascii=False, indent=2) + "\n",
    #     encoding="utf-8",
    # )
    pass


def after_all(ctx: HookContext) -> None:
    """全部版本同步完成后，成功和失败都会执行。"""
    pass


def on_success(ctx: HookContext) -> None:
    """版本同步成功后执行。"""
    pass


def on_failure(ctx: HookContext) -> None:
    """版本同步失败后执行。"""
    pass


def run(ctx: HookContext) -> None:
    """按固定顺序执行 version hook。"""
    before_all(ctx)
    try:
        sync_version_file(ctx)
        sync_package_json(ctx)
        sync_custom_files(ctx)
    except Exception:
        after_all(ctx)
        on_failure(ctx)
        raise
    else:
        after_all(ctx)
        on_success(ctx)


def main() -> None:
    """读取 payload 并执行 version hook。"""
    if len(sys.argv) != 2:
        raise SystemExit("usage: hook-version.py <payload.json>")

    payload_path = Path(sys.argv[1]).resolve()
    context = load_context(payload_path)
    run(context)
    print(f"hook-version completed for {context.git_tag or context.version}")


if __name__ == "__main__":
    main()
