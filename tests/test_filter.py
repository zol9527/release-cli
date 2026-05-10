"""提交过滤模块测试"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from release_cli.config import ReleaseConfig
from release_cli.filter import CommitFilter


def _make_config(tmp_path: Path, **overrides: object) -> ReleaseConfig:
    """创建测试用配置"""
    config: dict[str, object] = {
        "version": {"source": "file", "file": "VERSION"},
        "changelog": {"output_dir": "docs/changes"},
        "filter": {
            "ignore_messages": ["^docs:.*", "^chore:.*"],
            "keep_types": ["feat", "fix", "perf", "refactor", "security"],
        },
        "packager": {"root_dir": "."},
    }
    # 合并覆盖项
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)  # type: ignore[typeddict-item]
        else:
            config[key] = value

    config_file = tmp_path / ".release.yml"
    config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return ReleaseConfig(config_file)


class TestParseCommit:
    """_parse_commit 解析测试"""

    @pytest.fixture
    def cf(self, tmp_path: Path) -> CommitFilter:
        return CommitFilter(_make_config(tmp_path))

    # --- Conventional Commit 格式 ---

    def test_conventional_basic(self, cf: CommitFilter) -> None:
        result = cf._parse_commit("feat: add login")
        assert result is not None
        assert result.type == "feat"
        assert result.scope is None

    def test_conventional_with_scope(self, cf: CommitFilter) -> None:
        result = cf._parse_commit("feat(ui): add login button")
        assert result is not None
        assert result.type == "feat"
        assert result.scope == "ui"

    def test_conventional_fix(self, cf: CommitFilter) -> None:
        result = cf._parse_commit("fix(api): handle timeout")
        assert result is not None
        assert result.type == "fix"
        assert result.scope == "api"

    def test_conventional_case_insensitive(self, cf: CommitFilter) -> None:
        result = cf._parse_commit("Feat: something")
        assert result is not None
        assert result.type == "feat"

    # --- Emoji 格式 ---

    def test_emoji_feat(self, cf: CommitFilter) -> None:
        result = cf._parse_commit("✨ add login")
        assert result is not None
        assert result.type == "feat"
        assert result.scope is None

    def test_emoji_fix(self, cf: CommitFilter) -> None:
        result = cf._parse_commit("🐛 fix crash")
        assert result is not None
        assert result.type == "fix"

    def test_emoji_with_scope(self, cf: CommitFilter) -> None:
        result = cf._parse_commit("✨(ui): add login button")
        assert result is not None
        assert result.type == "feat"
        assert result.scope == "ui"

    # --- 无法识别的格式 ---

    def test_unrecognized_returns_none(self, cf: CommitFilter) -> None:
        assert cf._parse_commit("random message") is None

    def test_chore_not_in_keep_types_still_parses(self, cf: CommitFilter) -> None:
        """_parse_commit 只负责解析，不过滤"""
        result = cf._parse_commit("chore: update deps")
        assert result is not None
        assert result.type == "chore"


class TestShouldKeep:
    """_should_keep 过滤测试"""

    @pytest.fixture
    def cf(self, tmp_path: Path) -> CommitFilter:
        return CommitFilter(_make_config(tmp_path))

    def test_keeps_feat(self, cf: CommitFilter) -> None:
        assert cf._should_keep("feat: add login") is True

    def test_keeps_fix(self, cf: CommitFilter) -> None:
        assert cf._should_keep("fix: handle error") is True

    def test_keeps_emoji_feat(self, cf: CommitFilter) -> None:
        assert cf._should_keep("✨ add login") is True

    def test_rejects_docs(self, cf: CommitFilter) -> None:
        assert cf._should_keep("docs: update readme") is False

    def test_rejects_chore(self, cf: CommitFilter) -> None:
        assert cf._should_keep("chore: update deps") is False

    def test_rejects_unknown_type(self, cf: CommitFilter) -> None:
        assert cf._should_keep("random message") is False


class TestFilterCommits:
    """filter_commits 集成测试"""

    @pytest.fixture
    def cf(self, tmp_path: Path) -> CommitFilter:
        return CommitFilter(_make_config(tmp_path))

    def test_filters_mixed_commits(self, cf: CommitFilter) -> None:
        commits = [
            "feat: add login",
            "fix: handle error",
            "docs: update readme",
            "chore: update deps",
            "✨ new feature",
            "random message",
        ]
        result = cf.filter_commits(commits)
        assert result == ["feat: add login", "fix: handle error", "✨ new feature"]


class TestCategorizeCommits:
    """categorize_commits 分类测试"""

    @pytest.fixture
    def cf(self, tmp_path: Path) -> CommitFilter:
        return CommitFilter(_make_config(tmp_path))

    def test_categorizes_mixed_commits(self, cf: CommitFilter) -> None:
        commits = [
            "feat: add login",
            "feat(ui): add button",
            "✨ new dashboard",
            "fix: handle error",
            "🐛 fix crash",
            "perf: optimize query",
            "refactor: clean up",
            "unknown: something",
        ]
        result = cf.categorize_commits(commits)
        assert result["features"] == ["feat: add login", "feat(ui): add button", "✨ new dashboard"]
        assert result["fixes"] == ["fix: handle error", "🐛 fix crash"]
        assert result["perf"] == ["perf: optimize query"]
        assert result["refactor"] == ["refactor: clean up"]
        assert result["other"] == ["unknown: something"]


class TestCustomEmojiMap:
    """自定义 emoji_map 配置测试"""

    def test_custom_emoji_mapped(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            filter={
                "ignore_messages": [],
                "keep_types": ["feat", "fix"],
                "emoji_map": {"🚀": "feat", "🎉": "feat"},
            },
        )
        cf = CommitFilter(config)

        assert cf._should_keep("🚀 launch feature") is True
        assert cf._should_keep("🎉 celebration") is True

    def test_default_emoji_still_works_without_config(self, tmp_path: Path) -> None:
        """未配置 emoji_map 时使用默认映射"""
        cf = CommitFilter(_make_config(tmp_path))
        assert cf._should_keep("✨ add login") is True
        assert cf._should_keep("🐛 fix bug") is True
