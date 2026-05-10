from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from release_cli.cli import _build_release_tag, _ensure_release_files_ready, app
from release_cli.config import ReleaseConfig

runner = CliRunner()


def test_commit_command_help_hides_removed_version_and_date_options() -> None:
    result = runner.invoke(app, ["commit", "--help"])

    assert result.exit_code == 0
    assert "--all" in result.output
    assert "--version" not in result.output
    assert "--date" not in result.output


def test_commit_command_rejects_removed_version_option() -> None:
    result = runner.invoke(app, ["commit", "--version", "1.2.3"])

    assert result.exit_code != 0
    assert "No such option: --version" in result.output


def test_commit_command_rejects_removed_date_option() -> None:
    result = runner.invoke(app, ["commit", "--date", "2026-03-11"])

    assert result.exit_code != 0
    assert "No such option: --date" in result.output


def test_ensure_release_files_ready_checks_changelog_frontmatter_version(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n  source: file\n  file: VERSION\nchangelog:\n  output_dir: docs/changes\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )

    version_file = tmp_path / "VERSION"
    version_file.write_text("v1.2.3\n", encoding="utf-8")

    changelog_dir = tmp_path / "docs" / "changes"
    changelog_dir.mkdir(parents=True)
    changelog_path = changelog_dir / "2026-03-11-v1.2.3.md"
    changelog_path.write_text("---\nversion: \"1.2.4\"\n---\n", encoding="utf-8")

    subprocess.run(["git", "add", "VERSION", "docs/changes/2026-03-11-v1.2.3.md"], check=True, cwd=tmp_path, capture_output=True, text=True)

    config = ReleaseConfig(config_file)
    staged_files = {version_file.resolve(), changelog_path.resolve()}

    with pytest.raises(ValueError, match="与版本文件中的 v1.2.3 不一致"):
        _ensure_release_files_ready(config, staged_files, tmp_path)


def test_build_release_tag_uses_configured_tag_prefix(tmp_path: Path) -> None:
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  tag_prefix: backend/v\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )

    assert _build_release_tag(ReleaseConfig(config_file), "1.2.3") == "backend/v1.2.3"
