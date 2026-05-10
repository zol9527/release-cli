from __future__ import annotations

import subprocess
from pathlib import Path

from release_cli.config import ReleaseConfig
from release_cli.version import VersionManager, get_default_changelog_range


def test_git_tag_patch_bootstraps_from_initial_version_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n  source: git-tag\n  file: VERSION\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")

    vm = VersionManager(ReleaseConfig(config_file))

    assert vm.calculate_next("patch") == "0.1.0"


def test_git_tag_patch_bootstraps_to_default_when_version_file_missing(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n  source: git-tag\n  file: VERSION\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )

    vm = VersionManager(ReleaseConfig(config_file))

    assert vm.calculate_next("patch") == "0.1.0"


def test_git_tag_patch_still_uses_existing_release_tag_after_first_release(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, cwd=tmp_path, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "tag", "v0.1.0"], check=True, cwd=tmp_path, capture_output=True, text=True)

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n  source: git-tag\n  file: VERSION\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")

    vm = VersionManager(ReleaseConfig(config_file))

    assert vm.calculate_next("patch") == "0.1.1"


def test_git_tag_patch_uses_bootstrap_when_only_other_branch_has_tag(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, cwd=tmp_path, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", "release-side"], check=True, cwd=tmp_path, capture_output=True, text=True)
    (tmp_path / "side.txt").write_text("side\n", encoding="utf-8")
    subprocess.run(["git", "add", "side.txt"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "side release"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "tag", "v9.9.9"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-"], check=True, cwd=tmp_path, capture_output=True, text=True)

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n  source: git-tag\n  file: VERSION\npackager:\n  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")

    vm = VersionManager(ReleaseConfig(config_file))

    assert vm.calculate_next("patch") == "0.1.0"


def test_git_tag_prefix_isolates_monorepo_release_units(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, cwd=tmp_path, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "tag", "backend/v0.1.0"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "tag", "wechat/v9.9.9"], check=True, cwd=tmp_path, capture_output=True, text=True)

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  source: git-tag\n"
        "  file: VERSION\n"
        "  tag_prefix: backend/v\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )

    vm = VersionManager(ReleaseConfig(config_file))

    assert vm.calculate_next("patch") == "0.1.1"


def test_default_changelog_range_uses_tag_prefix(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, cwd=tmp_path, capture_output=True, text=True)

    (tmp_path / "README.md").write_text("first\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "feat: first"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "tag", "backend/v0.1.0"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "tag", "wechat/v9.9.9"], check=True, cwd=tmp_path, capture_output=True, text=True)

    (tmp_path / "README.md").write_text("second\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "fix: second"], check=True, cwd=tmp_path, capture_output=True, text=True)

    from_ref, to_ref = get_default_changelog_range(tmp_path, "backend/v")

    assert from_ref == "backend/v0.1.0"
    assert to_ref == "HEAD"
