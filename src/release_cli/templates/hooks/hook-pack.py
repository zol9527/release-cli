#!/usr/bin/env python3
"""release-cli pack hook 模板。

当 `packager.build.enabled: true` 时，release-cli pack 会先执行这个文件中的
build(ctx)，再执行 pack(ctx) 里的内置压缩逻辑。不同 workspace 的构建命令
通常差异很大，因此模板只保留清晰扩展点，不内置任何特定技术栈命令。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    class WorkflowContext:
        """release-cli pack hook 运行上下文（类型存根，仅供编辑器补全）。"""

        config: Any
        version: str
        tag: str
        step: str
        dry_run: bool

        @property
        def project_root(self) -> Path: ...
        @property
        def version_file(self) -> Path: ...
        @property
        def env(self) -> dict[str, str]: ...

        def builtin(self, name: str | None = None) -> None:
            """执行 release-cli 内置步骤。不传参则执行当前步骤。"""
            ...

        def run(
            self, command: list[str] | str, *, cwd: Path | None = None, shell: bool = False
        ) -> None:
            """执行命令。"""
            ...

        def output(self, command: list[str], *, cwd: Path | None = None) -> str:
            """执行命令并返回 stdout。"""
            ...


def before_all(ctx: WorkflowContext) -> None:
    """pack hook 开始前。"""
    pass


def before_step(ctx: WorkflowContext) -> None:
    """每个 pack 步骤执行前。"""
    pass


def build(ctx: WorkflowContext) -> None:
    """构建当前 workspace。

    示例：
        ctx.run(["bun", "run", "build"])
        ctx.run(["uv", "build", "--clear"])
        ctx.run(["bun", "run", "build:mp-weixin"])
    """
    pass


def pack(ctx: WorkflowContext) -> None:
    """执行 release-cli 内置压缩逻辑。"""
    ctx.builtin()


def after_step(ctx: WorkflowContext) -> None:
    """每个 pack 步骤执行后。"""
    pass


def after_all(ctx: WorkflowContext) -> None:
    """pack hook 结束后，成功和失败都会执行。"""
    pass


def on_success(ctx: WorkflowContext) -> None:
    """pack 成功后。"""
    pass


def on_failure(ctx: WorkflowContext) -> None:
    """pack 失败后。"""
    pass
