#!/usr/bin/env python3
"""release-cli release workflow 模板。

默认每个阶段都委托给 release-cli 内置实现。你可以在任意阶段前后补充
自己的检查、构建、通知或同步逻辑。
"""

from __future__ import annotations


def step(func):
    """标记一个函数为 workflow 阶段。

    这个模板故意不导入工具包代码，保证生成到项目里的脚本是自包含的。
    release-cli 运行时只读取这个标记，不要求项目把 release-cli 当成依赖包。
    """
    setattr(func, "__release_cli_step__", True)
    return func


@step
def preflight(ctx):
    """发布前检查。"""
    # 示例：增加项目自己的分支规则。
    # ctx.require_branch(r"^dev$", r"^hotfix/.+$")
    ctx.builtin()


@step
def prepare(ctx):
    """生成版本文件和 changelog。"""
    # 示例：prepare 前先跑测试。
    # ctx.run(["bun", "run", "test"])
    ctx.builtin()


@step
def commit(ctx):
    """提交发布文件并创建 tag。"""
    ctx.builtin()


@step
def pr(ctx):
    """创建发布 PR。默认配置下内置实现会跳过。"""
    ctx.builtin()
