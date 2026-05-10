from __future__ import annotations

from pathlib import Path

import pytest

from release_cli.cli import _read_changelog_frontmatter, _resolve_pack_version
from release_cli.config import ReleaseConfig


def test_read_changelog_frontmatter_reads_version(tmp_path: Path) -> None:
    changelog = tmp_path / "2026-03-10-v1.2.3.md"
    changelog.write_text(
        "---\nversion: \"1.2.3\"\ntitle: \"发布\"\n---\n\n## 新增功能\n",
        encoding="utf-8",
    )

    frontmatter = _read_changelog_frontmatter(changelog)

    assert frontmatter["version"] == "1.2.3"


def test_resolve_pack_version_uses_latest_changelog_version(tmp_path: Path) -> None:
    config_file = tmp_path / ".release.yml"
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    config_file.write_text(
        "changelog:\n  output_dir: docs/changes\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )

    older = changes_dir / "2026-03-10-v1.2.3.md"
    older.write_text("---\nversion: \"1.2.3\"\n---\n", encoding="utf-8")

    latest = changes_dir / "2026-03-11-v1.2.4.md"
    latest.write_text("---\nversion: \"1.2.4\"\n---\n", encoding="utf-8")

    version, changelog_path = _resolve_pack_version(ReleaseConfig(config_file))

    assert version == "1.2.4"
    assert changelog_path == latest.resolve()


def test_resolve_pack_version_ignores_non_release_markdown(tmp_path: Path) -> None:
    config_file = tmp_path / ".release.yml"
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    config_file.write_text(
        "changelog:\n  output_dir: docs/changes\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )

    (changes_dir / "README.md").write_text("# draft\n", encoding="utf-8")
    latest = changes_dir / "2026-03-11-v1.2.4.md"
    latest.write_text("---\nversion: \"1.2.4\"\n---\n", encoding="utf-8")

    version, changelog_path = _resolve_pack_version(ReleaseConfig(config_file))

    assert version == "1.2.4"
    assert changelog_path == latest.resolve()


def test_resolve_pack_version_prefers_higher_version_on_same_date(tmp_path: Path) -> None:
    config_file = tmp_path / ".release.yml"
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    config_file.write_text(
        "changelog:\n  output_dir: docs/changes\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )

    lower = changes_dir / "2026-03-11-v1.2.3.md"
    lower.write_text("---\nversion: \"1.2.3\"\n---\n", encoding="utf-8")

    higher = changes_dir / "2026-03-11-v1.2.4.md"
    higher.write_text("---\nversion: \"1.2.4\"\n---\n", encoding="utf-8")

    version, changelog_path = _resolve_pack_version(ReleaseConfig(config_file))

    assert version == "1.2.4"
    assert changelog_path == higher.resolve()


def test_resolve_pack_version_requires_valid_version(tmp_path: Path) -> None:
    config_file = tmp_path / ".release.yml"
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    config_file.write_text(
        "changelog:\n  output_dir: docs/changes\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )

    invalid = changes_dir / "2026-03-11-vinvalid.md"
    invalid.write_text("---\ntitle: \"发布\"\n---\n", encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        _resolve_pack_version(ReleaseConfig(config_file))


def test_read_changelog_frontmatter_raises_value_error_for_invalid_yaml(tmp_path: Path) -> None:
    changelog = tmp_path / "2026-03-11-v1.2.3.md"
    changelog.write_text("---\nversion: [1.2.3\n---\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML"):
        _read_changelog_frontmatter(changelog)


def test_resolve_pack_version_rejects_version_keyword(tmp_path: Path) -> None:
    config_file = tmp_path / ".release.yml"
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    config_file.write_text(
        "changelog:\n  output_dir: docs/changes\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )

    changelog = changes_dir / "2026-03-11-v1.2.4.md"
    changelog.write_text("---\nversion: \"patch\"\n---\n", encoding="utf-8")

    with pytest.raises(ValueError, match="明确版本号"):
        _resolve_pack_version(ReleaseConfig(config_file))


# ---------------------------------------------------------------------------
# changelog.root_dir 独立解析测试
# ---------------------------------------------------------------------------


def test_changelog_root_dir_resolves_independently_from_packager(tmp_path: Path) -> None:
    """changelog.root_dir 可以独立于 packager.root_dir 指定"""
    # 目录结构: project/.release/release.yml，项目根是 project/
    release_dir = tmp_path / ".release"
    release_dir.mkdir()
    config_file = release_dir / "release.yml"

    # changelog 输出到项目根下的 docs/changes
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)

    config_file.write_text(
        "changelog:\n"
        "  root_dir: ..\n"
        "  output_dir: docs/changes\n"
        "packager:\n"
        "  root_dir: ..\n",
        encoding="utf-8",
    )

    changelog = changes_dir / "2026-03-11-v2.0.0.md"
    changelog.write_text("---\nversion: \"2.0.0\"\n---\n", encoding="utf-8")

    version, changelog_path = _resolve_pack_version(ReleaseConfig(config_file))

    assert version == "2.0.0"
    assert changelog_path == changelog.resolve()


def test_changelog_root_dir_differs_from_packager_root_dir(tmp_path: Path) -> None:
    """changelog.root_dir 可以与 packager.root_dir 不同"""
    # 模拟配置文件在 project/.release/release.yml
    release_dir = tmp_path / ".release"
    release_dir.mkdir()
    config_file = release_dir / "release.yml"

    # changelog 输出到项目根的 changelog-output/ 目录（与 packager.root_dir 不同）
    custom_output = tmp_path / "changelog-output"
    custom_output.mkdir(parents=True)

    config_file.write_text(
        "changelog:\n"
        "  root_dir: ..\n"
        "  output_dir: changelog-output\n"
        "packager:\n"
        "  root_dir: ..\n",
        encoding="utf-8",
    )

    changelog = custom_output / "2026-03-11-v1.0.0.md"
    changelog.write_text("---\nversion: \"1.0.0\"\n---\n", encoding="utf-8")

    version, changelog_path = _resolve_pack_version(ReleaseConfig(config_file))

    assert version == "1.0.0"
    assert changelog_path == changelog.resolve()


def test_changelog_output_dir_falls_back_to_packager_root_dir(tmp_path: Path) -> None:
    """未配置 changelog.root_dir 时回退到 packager.root_dir（向后兼容）"""
    config_file = tmp_path / ".release.yml"
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)

    # 不配置 changelog.root_dir，只有 packager.root_dir
    config_file.write_text(
        "changelog:\n"
        "  output_dir: docs/changes\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )

    changelog = changes_dir / "2026-03-11-v1.0.0.md"
    changelog.write_text("---\nversion: \"1.0.0\"\n---\n", encoding="utf-8")

    config = ReleaseConfig(config_file)
    # 向后兼容：changelog_root_dir 回退到 packager_root_dir
    assert config.changelog_root_dir == config.packager_root_dir

    version, changelog_path = _resolve_pack_version(config)

    assert version == "1.0.0"
    assert changelog_path == changelog.resolve()
