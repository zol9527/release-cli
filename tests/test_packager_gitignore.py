from __future__ import annotations

import subprocess
import zipfile
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from release_cli.cli import app
from release_cli.config import ReleaseConfig
from release_cli.packager import Packager

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=path, capture_output=True, text=True)


def test_packager_can_respect_gitignore_rules(tmp_path: Path) -> None:
    """packager.respect_gitignore 会复用 Git ignore 规则过滤候选文件"""
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text(
        "build/\n*.log\n!important.log\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "cache.bin").write_text("cache\n", encoding="utf-8")
    (tmp_path / "debug.log").write_text("debug\n", encoding="utf-8")
    (tmp_path / "important.log").write_text("keep\n", encoding="utf-8")

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "packager:\n"
        "  root_dir: .\n"
        "  output_dir: release\n"
        "  respect_gitignore: true\n"
        "  include:\n"
        "    - '*'\n"
        "  exclude:\n"
        "    - .git\n",
        encoding="utf-8",
    )

    output_path = Packager(ReleaseConfig(config_file)).create_package("1.0.0")

    with zipfile.ZipFile(output_path) as archive:
        names = set(archive.namelist())

    assert "src/app.py" in names
    assert "important.log" in names
    assert "debug.log" not in names
    assert "build/cache.bin" not in names


def test_packager_star_include_collects_hidden_entries(tmp_path: Path) -> None:
    """include 的 * 会收集隐藏文件和隐藏目录"""
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release" / "release.yml").write_text("release\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("env\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("app\n", encoding="utf-8")

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "packager:\n  root_dir: .\n  output_dir: release\n  include:\n    - '*'\n  exclude: []\n",
        encoding="utf-8",
    )

    output_path = Packager(ReleaseConfig(config_file)).create_package("1.0.0")

    with zipfile.ZipFile(output_path) as archive:
        names = set(archive.namelist())

    assert ".release/release.yml" in names
    assert ".env.example" in names
    assert "app.txt" in names


def test_packager_keeps_ignored_files_when_gitignore_option_is_disabled(tmp_path: Path) -> None:
    """未开启 respect_gitignore 时保持旧行为, 只应用 packager.exclude"""
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n*.log\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "cache.bin").write_text("cache\n", encoding="utf-8")
    (tmp_path / "debug.log").write_text("debug\n", encoding="utf-8")

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "packager:\n"
        "  root_dir: .\n"
        "  output_dir: release\n"
        "  include:\n"
        "    - '*'\n"
        "  exclude:\n"
        "    - .git\n",
        encoding="utf-8",
    )

    output_path = Packager(ReleaseConfig(config_file)).create_package("1.0.0")

    with zipfile.ZipFile(output_path) as archive:
        names = set(archive.namelist())

    assert "debug.log" in names
    assert "build/cache.bin" in names


def test_packager_force_include_runs_after_gitignore_and_exclude(tmp_path: Path) -> None:
    """force_include 可以在 gitignore 和 exclude 过滤后加回特例文件"""
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "cache.bin").write_text("cache\n", encoding="utf-8")
    (tmp_path / "build" / "keep.txt").write_text("keep\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("app\n", encoding="utf-8")

    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "packager:\n"
        "  root_dir: .\n"
        "  output_dir: release\n"
        "  respect_gitignore: true\n"
        "  include:\n"
        "    - '*'\n"
        "  exclude:\n"
        "    - .git\n"
        "    - secret.txt\n"
        "  force_include:\n"
        "    - build/keep.txt\n"
        "    - secret.txt\n",
        encoding="utf-8",
    )

    output_path = Packager(ReleaseConfig(config_file)).create_package("1.0.0")

    with zipfile.ZipFile(output_path) as archive:
        names = set(archive.namelist())

    assert "app.txt" in names
    assert "build/keep.txt" in names
    assert "secret.txt" in names
    assert "build/cache.bin" not in names


def test_pack_command_skips_build_hook_when_build_disabled(tmp_path: Path) -> None:
    """packager.build.enabled=false 时只压缩 workspace，不执行 build hook"""
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    (changes_dir / "2026-03-11-v1.0.0.md").write_text("---\nversion: \"1.0.0\"\n---\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("app\n", encoding="utf-8")
    hook_file = tmp_path / "hook-pack.py"
    hook_file.write_text(
        "def build(ctx):\n"
        "    (ctx.project_root / 'built.txt').write_text('built', encoding='utf-8')\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "changelog:\n"
        "  output_dir: docs/changes\n"
        "packager:\n"
        "  root_dir: .\n"
        "  output_dir: release\n"
        "  build:\n"
        "    enabled: false\n"
        "    script: hook-pack.py\n"
        "  include:\n"
        "    - '*'\n"
        "  exclude:\n"
        "    - release\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--config", str(config_file), "pack"])

    assert result.exit_code == 0
    assert not (tmp_path / "built.txt").exists()


def test_pack_command_runs_build_hook_before_archiving_when_build_enabled(tmp_path: Path) -> None:
    """packager.build.enabled=true 时先执行 build hook，再压缩构建产物"""
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    (changes_dir / "2026-03-11-v1.0.0.md").write_text("---\nversion: \"1.0.0\"\n---\n", encoding="utf-8")
    hook_file = tmp_path / "hook-pack.py"
    hook_file.write_text(
        "def build(ctx):\n"
        "    (ctx.project_root / 'dist').mkdir(exist_ok=True)\n"
        "    (ctx.project_root / 'dist' / 'app.txt').write_text(ctx.version, encoding='utf-8')\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "changelog:\n"
        "  output_dir: docs/changes\n"
        "packager:\n"
        "  root_dir: .\n"
        "  output_dir: release\n"
        "  build:\n"
        "    enabled: true\n"
        "    script: hook-pack.py\n"
        "  include:\n"
        "    - dist\n"
        "  exclude:\n"
        "    - release\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--config", str(config_file), "pack"])

    assert result.exit_code == 0
    output_path = tmp_path / "release" / f"{tmp_path.name}-1.0.0.zip"
    with zipfile.ZipFile(output_path) as archive:
        assert archive.read("dist/app.txt").decode() == "1.0.0"


def test_pack_command_requires_script_when_build_enabled(tmp_path: Path) -> None:
    """packager.build.enabled=true 但未配置 script 时给出明确错误"""
    changes_dir = tmp_path / "docs" / "changes"
    changes_dir.mkdir(parents=True)
    (changes_dir / "2026-03-11-v1.0.0.md").write_text("---\nversion: \"1.0.0\"\n---\n", encoding="utf-8")
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "changelog:\n"
        "  output_dir: docs/changes\n"
        "packager:\n"
        "  root_dir: .\n"
        "  build:\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--config", str(config_file), "pack"])

    assert result.exit_code != 0
    assert "packager.build.script" in result.output
