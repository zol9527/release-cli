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


class CommitFilter:
    """提交过滤器"""

    # 常见的 Emoji 和对应的提交类型
    EMOJI_MAP = {
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

    def __init__(self, config: ReleaseConfig):
        self.config = config

    def filter_commits(self, commits: list[str]) -> list[str]:
        """过滤提交列表"""
        filtered = []

        for commit in commits:
            if self._should_keep(commit):
                filtered.append(commit)

        return filtered

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

        for commit_type in keep_types:
            # 检查传统格式: feat:, fix:, perf:
            if re.search(rf"^{commit_type}\b", commit_lower):
                return True

            # 检查带括号格式: feat(ui):
            if re.search(rf"^{commit_type}\([^)]+\):", commit_lower):
                return True

            # 检查 Emoji 格式
            for emoji in self._get_emojis_for_type(commit_type):
                if commit.startswith(emoji):
                    return True

        return False

    def _get_emojis_for_type(self, commit_type: str) -> list[str]:
        """获取类型对应的所有 Emoji"""
        return [emoji for emoji, ctype in self.EMOJI_MAP.items() if ctype == commit_type]

    def categorize_commits(self, commits: list[str]) -> dict[str, list[str]]:
        """分类提交"""
        categories = {
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
        """识别提交类型，兼容 conventional commit 与 emoji 风格"""
        commit_lower = commit.lower().strip()

        for commit_type in ["feat", "fix", "perf", "refactor", "security"]:
            if re.search(rf"^{commit_type}\b", commit_lower):
                return commit_type
            if re.search(rf"^{commit_type}\([^)]+\):", commit_lower):
                return commit_type

        for emoji, commit_type in self.EMOJI_MAP.items():
            if commit.startswith(emoji):
                return commit_type

        return None


def filter_commits(commits: list[str], config_path: str | None = None) -> list[str]:
    """过滤提交（便捷函数）"""
    config = ReleaseConfig(config_path)
    cf = CommitFilter(config)
    return cf.filter_commits(commits)
