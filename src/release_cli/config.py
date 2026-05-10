"""配置管理模块"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class ReleaseConfig:
    """发布配置类"""

    DEFAULT_CONFIG_FILE = ".release/release.yml"

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path or self.DEFAULT_CONFIG_FILE)
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """加载配置文件"""
        if not self.config_path.exists():
            # 如果配置文件不存在，使用默认配置
            self._config = self._default_config()
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

        # 合并环境特定配置
        env = os.environ.get("RELEASE_ENV", "default")
        env_config = self._config.get("environments", {}).get(env, {})
        if env_config:
            self._merge_env_config(env_config)

    def _default_config(self) -> dict[str, Any]:
        """默认配置"""
        return {
            "version": {
                "source": "file",
                "tag_prefix": "v",
                "file": "VERSION",
            },
            "changelog": {
                "output_dir": "docs/changes",
            },
            "filter": {
                "ignore_messages": ["^docs:.*", "^chore:.*", "^style:.*", ".*WIP.*", ".*merge.*", "^Revert.*"],
                "keep_types": ["feat", "fix", "perf", "refactor", "security"],
            },
            "release": {
                "steps": ["preflight", "prepare", "commit", "pr"],
                "allowed_branches": [],
                "auto_stage": True,
                "create_pr": False,
                "push": False,
                "base_branch": "release",
                "hooks": {},
            },
            "packager": {
                "name": "{name}-{version}",
                "root_dir": ".",
                "output_dir": "release",
                "include": ["*", ".*"],
                "exclude": [".git", ".github", ".beads", ".venv", "node_modules", "release"],
            },
        }

    def _merge_env_config(self, env_config: dict[str, Any]) -> None:
        """合并环境特定配置"""
        for key, value in env_config.items():
            if key in self._config and isinstance(value, dict):
                self._config[key].update(value)
            else:
                self._config[key] = value

    def reload(self) -> None:
        """重新加载配置"""
        self._load()

    @property
    def base_dir(self) -> Path:
        """配置文件所在目录"""
        return self.config_path.resolve().parent

    def _resolve_path(self, value: str | Path) -> Path:
        """将相对路径解析为相对配置文件的路径"""
        path = Path(value)
        if path.is_absolute():
            return path

        return (self.base_dir / path).resolve()

    @property
    def version_source(self) -> str:
        """版本来源: file | git-tag"""
        return self._config.get("version", {}).get("source", "file")

    @property
    def version_tag_prefix(self) -> str:
        """Git tag 前缀, 用于 monorepo 中隔离不同发布单元"""
        return self._config.get("version", {}).get("tag_prefix", "v")

    @property
    def version_file(self) -> Path:
        """VERSION 文件路径"""
        file_path = self._config.get("version", {}).get("file", "VERSION")
        return self._resolve_path(file_path)

    @property
    def version_hook(self) -> Path | None:
        """写入版本后执行的 Hook 脚本"""
        hook = self._config.get("version", {}).get("hook")
        if not hook:
            return None

        return self._resolve_path(hook)

    @property
    def filter_config(self) -> dict[str, Any]:
        """提交过滤配置"""
        return self._config.get("filter", {})

    @property
    def changelog_output_dir(self) -> Path:
        """changelog 输出目录"""
        output_dir = self._config.get("changelog", {}).get("output_dir", "docs/changes")
        output_path = Path(output_dir)
        if output_path.is_absolute():
            return output_path

        return (self.packager_root_dir / output_path).resolve()

    @property
    def ignore_messages(self) -> list[str]:
        """忽略的提交消息规则"""
        return self.filter_config.get("ignore_messages", [])

    @property
    def keep_types(self) -> list[str]:
        """保留的提交类型"""
        return self.filter_config.get("keep_types", ["feat", "fix", "perf", "refactor", "security"])

    @property
    def release_config(self) -> dict[str, Any]:
        """发布流水线配置"""
        return self._config.get("release", {})

    @property
    def workflow_config(self) -> dict[str, Any]:
        """用户自定义 workflow 配置"""
        return self._config.get("workflow", {})

    def workflow_script(self, name: str) -> Path | None:
        """读取指定 workflow 的 Python 脚本路径"""
        workflow = self.workflow_config.get(name, {})
        if not isinstance(workflow, dict):
            return None
        script = workflow.get("script")
        if not script:
            return None
        return self._resolve_path(str(script))

    @property
    def release_steps(self) -> list[str]:
        """发布流水线步骤"""
        steps = self.release_config.get("steps", ["preflight", "prepare", "commit", "pr"])
        return [str(step).strip() for step in steps if str(step).strip()]

    @property
    def release_allowed_branches(self) -> list[str]:
        """允许执行发布的分支正则列表，空列表表示不限制"""
        patterns = self.release_config.get("allowed_branches", [])
        return [str(pattern).strip() for pattern in patterns if str(pattern).strip()]

    @property
    def release_auto_stage(self) -> bool:
        """commit 阶段是否自动暂存发布相关文件"""
        return bool(self.release_config.get("auto_stage", True))

    @property
    def release_create_pr(self) -> bool:
        """是否在 release 流水线中创建 PR"""
        return bool(self.release_config.get("create_pr", False))

    @property
    def release_push(self) -> bool:
        """创建 PR 前是否推送当前分支"""
        return bool(self.release_config.get("push", False))

    @property
    def release_base_branch(self) -> str:
        """发布 PR 的目标分支"""
        return str(self.release_config.get("base_branch", "release")).strip() or "release"

    @property
    def release_hooks(self) -> dict[str, list[str]]:
        """发布流水线阶段 hook 命令"""
        hooks = self.release_config.get("hooks", {})
        if not isinstance(hooks, dict):
            return {}

        normalized: dict[str, list[str]] = {}
        for name, commands in hooks.items():
            if isinstance(commands, str):
                normalized[str(name)] = [commands]
                continue
            if isinstance(commands, list):
                normalized[str(name)] = [str(command) for command in commands if str(command).strip()]
        return normalized

    def resolve_project_path(self, value: str | Path) -> Path:
        """将路径解析为相对发布单元根目录的绝对路径"""
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.packager_root_dir / path).resolve()

    @property
    def packager_type(self) -> str:
        """打包器类型"""
        return "zip"

    @property
    def packager_name(self) -> str:
        """打包文件名模板"""
        return self._config.get("packager", {}).get("name", "{name}-{version}")

    @property
    def packager_root_dir(self) -> Path:
        """打包项目根目录"""
        root_dir = self._config.get("packager", {}).get("root_dir", ".")
        return self._resolve_path(root_dir)

    @property
    def packager_output_dir(self) -> Path:
        """打包输出目录"""
        output_dir = self._config.get("packager", {}).get("output_dir", "release")
        output_path = Path(output_dir)
        if output_path.is_absolute():
            return output_path

        return (self.packager_root_dir / output_path).resolve()

    @property
    def packager_include(self) -> list[str]:
        """打包包含的文件"""
        return self._config.get("packager", {}).get("include", ["*"])

    @property
    def packager_exclude(self) -> list[str]:
        """打包排除的文件"""
        return self._config.get("packager", {}).get("exclude", [])


def load_config(config_path: str | Path | None = None) -> ReleaseConfig:
    """加载配置"""
    return ReleaseConfig(config_path)
