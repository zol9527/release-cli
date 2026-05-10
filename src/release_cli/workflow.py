"""用户自定义 workflow 的轻量运行时 API。"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


StepFunc = Callable[["WorkflowContext"], None]


def step(func: StepFunc) -> StepFunc:
    """标记一个函数为 release-cli workflow 阶段。"""
    setattr(func, "__release_cli_step__", True)
    return func


@dataclass(frozen=True)
class WorkflowContext:
    """自定义 workflow 阶段的运行上下文。"""

    config: Any
    version: str
    tag: str
    step: str
    dry_run: bool
    builtin_runner: Callable[[str], None]

    @property
    def project_root(self) -> Path:
        """当前发布单元根目录。"""
        return self.config.packager_root_dir

    @property
    def version_file(self) -> Path:
        """当前发布单元版本文件。"""
        return self.config.version_file

    @property
    def env(self) -> dict[str, str]:
        """传给子进程的标准 release 环境变量。"""
        env = dict(os.environ)
        env.update(
            {
                "RELEASE_STEP": self.step,
                "RELEASE_VERSION": self.version,
                "RELEASE_TAG": self.tag,
                "RELEASE_PROJECT_ROOT": str(self.project_root),
                "RELEASE_CONFIG": str(self.config.config_path.resolve()),
                "RELEASE_VERSION_FILE": str(self.version_file),
            }
        )
        return env

    def builtin(self, name: str | None = None) -> None:
        """执行 release-cli 内置阶段逻辑。"""
        self.builtin_runner(name or self.step)

    def run(self, command: list[str] | str, *, cwd: Path | None = None, shell: bool = False) -> None:
        """执行命令；dry-run 时只打印不执行。"""
        display = command if isinstance(command, str) else " ".join(command)
        print(f"    $ {display}")
        if self.dry_run:
            return
        subprocess.run(command, cwd=cwd or self.project_root, env=self.env, shell=shell, check=True)

    def output(self, command: list[str], *, cwd: Path | None = None) -> str:
        """执行命令并返回 stdout。"""
        result = subprocess.run(
            command,
            cwd=cwd or self.project_root,
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def require_clean_git(self) -> None:
        """要求工作区没有未提交变更。"""
        dirty = self.output(["git", "status", "--short"])
        if dirty:
            raise RuntimeError("工作区存在未提交变更，请先清理")

    def require_branch(self, *patterns: str) -> None:
        """要求当前分支匹配任一正则。"""
        branch = self.output(["git", "symbolic-ref", "--short", "-q", "HEAD"])
        if not branch:
            raise RuntimeError("当前处于 detached HEAD，无法执行该 workflow")
        if not any(re.fullmatch(pattern, branch) for pattern in patterns):
            raise RuntimeError(f"当前分支 {branch} 不符合要求: {', '.join(patterns)}")

    def git_add(self, *paths: str) -> None:
        """暂存文件。"""
        self.run(["git", "add", "--", *paths])

    def git_commit(self, message: str) -> None:
        """创建 Git commit。"""
        self.run(["git", "commit", "-m", message])
