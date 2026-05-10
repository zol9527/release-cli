"""提交过滤模块"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .config import ReleaseConfig


@dataclass
class Commit:
    """提交信息"""
    message: str
    hash: str | None = None
    author: str | None = None
    date: str | None = None


@dataclass
class ParsedCommit:
    """解析后的提交信息"""
    type: str
    scope: str | None = None


# 默认 Emoji 映射（当配置文件中未指定 emoji_map 时使用）
_DEFAULT_EMOJI_MAP: dict[str, str] = {
    "✨": "feat",
    "🐛": "fix",
    "🛡️": "security",
    "🛡": "security",
    "⚡️": "perf",
    "⚡": "perf",
    "♻️": "refactor",
    "♻": "refactor",
    "🔒": "security",
    "🔐": "security",
    "🔧": "chore",
    "💄": "style",
    "✅": "test",
    "📝": "docs",
    "📄": "docs",
}


class CommitFilter:
    """提交过滤器"""

    def __init__(self, config: ReleaseConfig):
        self.config = config
        # 配置文件中的 emoji_map 优先，否则使用默认映射
        config_emoji_map = config.emoji_map
        self.emoji_map: dict[str, str] = config_emoji_map if config_emoji_map else dict(_DEFAULT_EMOJI_MAP)

    def filter_commits(self, commits: list[str]) -> list[str]:
        """过滤提交列表"""
        return [commit for commit in commits if self._should_keep(commit)]

    def _parse_commit(self, commit: str) -> ParsedCommit | None:
        """统一解析提交消息，提取类型和 scope

        支持以下格式:
          - feat: message           → type=feat, scope=None
          - feat(ui): message       → type=feat, scope=ui
          - ✨ message              → type=feat, scope=None
          - ✨(ui): message         → type=feat, scope=ui
        """
        commit_lower = commit.lower().strip()

        # 1. 尝试匹配 conventional commit 格式: type(scope): message
        match = re.match(r"^(\w+)(?:\(([^)]+)\))?\s*:", commit_lower)
        if match:
            return ParsedCommit(type=match.group(1), scope=match.group(2))

        # 2. 尝试匹配 emoji 格式
        for emoji, commit_type in self.emoji_map.items():
            if commit.startswith(emoji):
                # emoji 后可能带 (scope): 格式
                rest = commit[len(emoji):].strip()
                scope_match = re.match(r"^\(([^)]+)\)\s*:", rest)
                scope = scope_match.group(1) if scope_match else None
                return ParsedCommit(type=commit_type, scope=scope)

        return None

    def _should_keep(self, commit: str) -> bool:
        """判断是否保留提交"""
        commit_lower = commit.lower()

        # 1. 检查是否匹配忽略规则（黑名单）
        for pattern in self.config.ignore_messages:
            try:
                if re.match(pattern, commit, re.IGNORECASE):
                    return False
            except re.error:
                # 如果正则表达式无效，尝试字面匹配
                if pattern.lower() in commit_lower:
                    return False

        # 2. 检查是否匹配保留类型（白名单）
        keep_types = self.config.keep_types
        if not keep_types:
            return True

        parsed = self._parse_commit(commit)
        if parsed and parsed.type in keep_types:
            return True

        return False

    def categorize_commits(self, commits: list[str]) -> dict[str, list[str]]:
        """分类提交"""
        categories: dict[str, list[str]] = {
            "features": [],
            "fixes": [],
            "perf": [],
            "refactor": [],
            "security": [],
            "other": [],
        }

        for commit in commits:
            commit_type = self._detect_commit_type(commit)

            if commit_type == "feat":
                categories["features"].append(commit)
            elif commit_type == "fix":
                categories["fixes"].append(commit)
            elif commit_type == "perf":
                categories["perf"].append(commit)
            elif commit_type == "refactor":
                categories["refactor"].append(commit)
            elif commit_type == "security":
                categories["security"].append(commit)
            else:
                categories["other"].append(commit)

        return categories

    def _detect_commit_type(self, commit: str) -> str | None:
        """识别提交类型"""
        parsed = self._parse_commit(commit)
        return parsed.type if parsed else None


def filter_commits(commits: list[str], config_path: str | None = None) -> list[str]:
    """过滤提交（便捷函数）"""
    config = ReleaseConfig(config_path)
    cf = CommitFilter(config)
    return cf.filter_commits(commits)
