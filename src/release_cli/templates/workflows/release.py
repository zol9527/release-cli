#!/usr/bin/env python3
"""release-cli release workflow 模板。

默认每个阶段都委托给 release-cli 内置实现。你可以在任意阶段前后补充
自己的检查、构建、通知或同步逻辑。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    class WorkflowContext:
        """release-cli workflow 运行上下文（类型存根，仅供编辑器补全）。

        由 release-cli 运行时注入真实实现，用户代码不需要导入或构造。
        """

        # ── 数据属性 ──────────────────────────────────────
        config: Any
        version: str
        tag: str
        step: str
        dry_run: bool

        # ── 派生属性 ──────────────────────────────────────
        @property
        def project_root(self) -> Path: ...
        @property
        def version_file(self) -> Path: ...
        @property
        def env(self) -> dict[str, str]: ...

        # ── 核心方法 ──────────────────────────────────────
        def builtin(self, name: str | None = None) -> None:
            """执行 release-cli 内置阶段逻辑。不传参则执行当前步骤。"""
            ...

        def run(
            self, command: list[str] | str, *, cwd: Path | None = None, shell: bool = False
        ) -> None:
            """执行命令；dry-run 时只打印不执行。"""
            ...

        def output(self, command: list[str], *, cwd: Path | None = None) -> str:
            """执行命令并返回 stdout。"""
            ...

        # ── Git 操作 ──────────────────────────────────────
        def git_add(self, *paths: str) -> None:
            """暂存文件。"""
            ...

        def git_commit(self, message: str) -> None:
            """创建 Git commit。"""
            ...

        # ── 前置检查 ──────────────────────────────────────
        def require_clean_git(self) -> None:
            """要求工作区没有未提交变更，否则抛异常。"""
            ...

        def require_branch(self, *patterns: str) -> None:
            """要求当前分支匹配任一正则，否则抛异常。"""
            ...


def step(func):
    """标记一个函数为 workflow 阶段。

    这个模板故意不导入工具包代码，保证生成到项目里的脚本是自包含的。
    release-cli 运行时只读取这个标记，不要求项目把 release-cli 当成依赖包。
    """
    setattr(func, "__release_cli_step__", True)
    return func


# -----------------------------------------------------------------------------
# 生命周期 hook（不需要 @step 装饰器，函数名匹配即自动识别）
# -----------------------------------------------------------------------------


def before_all(ctx: WorkflowContext) -> None:
    """整个 release workflow 开始前。"""
    pass


def before_step(ctx: WorkflowContext) -> None:
    """每个已定义阶段执行前。"""
    pass


def after_step(ctx: WorkflowContext) -> None:
    """每个已定义阶段执行后。"""
    pass


# -----------------------------------------------------------------------------
# 流水线阶段（需要 @step 装饰器）
# -----------------------------------------------------------------------------
# 在 ctx.builtin() 上下方添加代码即可实现 pre/post 操作：
#   @step
#   def prepare(ctx):
#       ctx.run(["make", "test"])       # pre: 内置逻辑前
#       ctx.builtin()                   # 内置逻辑（写 VERSION、生成 changelog）
#       ctx.run(["python", "notify.py"]) # post: 内置逻辑后
# -----------------------------------------------------------------------------


@step
def preflight(ctx: WorkflowContext) -> None:
    """发布前检查。"""
    # 示例：增加项目自己的分支规则。
    # ctx.require_branch(r"^dev$", r"^hotfix/.+$")
    ctx.builtin()


@step
def prepare(ctx: WorkflowContext) -> None:
    """生成版本文件和 changelog。"""
    # 示例：prepare 前先跑测试。
    # ctx.run(["bun", "run", "test"])
    ctx.builtin()


@step
def commit(ctx: WorkflowContext) -> None:
    """提交发布文件并创建 tag。"""
    ctx.builtin()


@step
def pr(ctx: WorkflowContext) -> None:
    """创建发布 PR。默认配置下内置实现会跳过。"""
    ctx.builtin()


# -----------------------------------------------------------------------------
# 生命周期 hook（收尾）
# -----------------------------------------------------------------------------


def after_all(ctx: WorkflowContext) -> None:
    """整个 release workflow 结束后，成功和失败都会执行。"""
    pass


def on_success(ctx: WorkflowContext) -> None:
    """全部已定义阶段成功后执行。"""
    pass


def on_failure(ctx: WorkflowContext) -> None:
    """任意阶段失败后执行。"""
    pass
