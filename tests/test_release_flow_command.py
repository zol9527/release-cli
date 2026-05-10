from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from release_cli.cli import app


runner = CliRunner()


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, cwd=path, capture_output=True, text=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "feat: init"], check=True, cwd=path, capture_output=True, text=True)


def test_release_flow_dry_run_can_stop_at_prepare(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  source: git-tag\n"
        "  tag_prefix: backend/v\n"
        "  file: VERSION\n"
        "changelog:\n"
        "  output_dir: docs/changes\n"
        "release:\n"
        "  steps: [preflight, prepare, commit, pr]\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "VERSION", ".release.yml"], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "chore: add release config"], check=True, cwd=tmp_path, capture_output=True, text=True)

    result = runner.invoke(app, ["--config", str(config_file), "release", "patch", "--dry-run", "--to-step", "prepare"])

    assert result.exit_code == 0
    assert "preflight -> prepare" in result.output
    assert "backend/v0.1.0" in result.output
    assert not (tmp_path / "docs" / "changes").exists()


def test_release_flow_rejects_unknown_step(tmp_path: Path) -> None:
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "release:\n"
        "  steps: [preflight, unknown]\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--config", str(config_file), "release", "patch", "--dry-run"])

    assert result.exit_code != 0
    assert "不支持的 release 步骤" in result.output


def test_release_flow_can_run_custom_python_workflow(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    workflow_path = tmp_path / ".release" / "_shared" / "hooks" / "hook-release.py"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        "def step(func):\n"
        "    setattr(func, '__release_cli_step__', True)\n"
        "    return func\n\n"
        "@step\n"
        "def preflight(ctx):\n"
        "    print(f'custom {ctx.tag}')\n"
        "    ctx.builtin()\n\n"
        "@step\n"
        "def prepare(ctx):\n"
        "    ctx.builtin()\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  source: git-tag\n"
        "  tag_prefix: backend/v\n"
        "  file: VERSION\n"
        "workflow:\n"
        "  release:\n"
        "    script: .release/_shared/hooks/hook-release.py\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "chore: add workflow"], check=True, cwd=tmp_path, capture_output=True, text=True)

    result = runner.invoke(app, ["--config", str(config_file), "release", "patch", "--dry-run", "--to-step", "prepare"])

    assert result.exit_code == 0
    assert "Workflow Script" in result.output
    assert "custom backend/v0.1.0" in result.output


def test_init_monorepo_generates_unit_configs_and_shared_workflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--monorepo", "--units", "backend,wechat"])

    assert result.exit_code == 0
    assert (tmp_path / ".release" / "backend.yml").exists()
    assert (tmp_path / ".release" / "wechat.yml").exists()
    assert (tmp_path / ".release" / "_shared" / "hooks" / "hook-version.py").exists()
    assert (tmp_path / ".release" / "_shared" / "hooks" / "hook-release.py").exists()
    assert (tmp_path / ".release" / "_state" / "backend.VERSION").exists()
    assert (tmp_path / ".release" / "_state" / "wechat.VERSION").exists()
    assert 'tag_prefix: "backend/v"' in (tmp_path / ".release" / "backend.yml").read_text(encoding="utf-8")
    assert "release_cli.workflow" not in (tmp_path / ".release" / "_shared" / "hooks" / "hook-release.py").read_text(encoding="utf-8")


def test_init_single_project_generates_everything_under_release_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert (tmp_path / ".release" / "release.yml").exists()
    assert (tmp_path / ".release" / "_state" / "VERSION").exists()
    assert (tmp_path / ".release" / "_shared" / "hooks" / "hook-version.py").exists()
    assert (tmp_path / ".release" / "_shared" / "hooks" / "hook-release.py").exists()
    assert not (tmp_path / ".release.yml").exists()
    assert not (tmp_path / "VERSION").exists()
    assert not (tmp_path / "scripts" / "release-version-hook.py").exists()


def test_release_flow_can_load_plain_named_step_functions(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    workflow_path = tmp_path / "release.py"
    workflow_path.write_text(
        "def preflight(ctx):\n"
        "    print(f'plain {ctx.tag}')\n"
        "    ctx.builtin()\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  source: git-tag\n"
        "  tag_prefix: app/v\n"
        "  file: VERSION\n"
        "workflow:\n"
        "  release:\n"
        "    script: release.py\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "chore: add workflow"], check=True, cwd=tmp_path, capture_output=True, text=True)

    result = runner.invoke(app, ["--config", str(config_file), "release", "patch", "--dry-run", "--only", "preflight"])

    assert result.exit_code == 0
    assert "plain app/v0.1.0" in result.output


def test_release_flow_skips_missing_custom_workflow_steps(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    workflow_path = tmp_path / "release.py"
    workflow_path.write_text(
        "def prepare(ctx):\n"
        "    print('prepare only')\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  source: git-tag\n"
        "  tag_prefix: app/v\n"
        "  file: VERSION\n"
        "workflow:\n"
        "  release:\n"
        "    script: release.py\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "chore: add workflow"], check=True, cwd=tmp_path, capture_output=True, text=True)

    result = runner.invoke(app, ["--config", str(config_file), "release", "patch", "--dry-run", "--to-step", "prepare"])

    assert result.exit_code == 0
    assert "[preflight] workflow 未定义，跳过" in result.output
    assert "prepare only" in result.output


def test_release_flow_runs_lifecycle_functions_in_python_workflow(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    workflow_path = tmp_path / "release.py"
    workflow_path.write_text(
        "def before_all(ctx):\n"
        "    print('before_all')\n"
        "def before_step(ctx):\n"
        "    print(f'before_step:{ctx.step}')\n"
        "def prepare(ctx):\n"
        "    print('prepare')\n"
        "def after_step(ctx):\n"
        "    print(f'after_step:{ctx.step}')\n"
        "def after_all(ctx):\n"
        "    print('after_all')\n"
        "def on_success(ctx):\n"
        "    print('on_success')\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  source: git-tag\n"
        "  tag_prefix: app/v\n"
        "  file: VERSION\n"
        "workflow:\n"
        "  release:\n"
        "    script: release.py\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION").write_text("v0.1.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], check=True, cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "chore: add workflow"], check=True, cwd=tmp_path, capture_output=True, text=True)

    result = runner.invoke(app, ["--config", str(config_file), "release", "patch", "--dry-run", "--only", "prepare"])

    assert result.exit_code == 0
    expected_order = [
        "before_all",
        "before_step:prepare",
        "prepare",
        "after_step:prepare",
        "after_all",
        "on_success",
    ]
    output_lines = [line.strip() for line in result.output.splitlines()]
    lifecycle_lines = [line for line in output_lines if line in expected_order]
    assert lifecycle_lines == expected_order


def test_release_flow_runs_on_failure_in_python_workflow(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    workflow_path = tmp_path / "release.py"
    workflow_path.write_text(
        "def prepare(ctx):\n"
        "    raise RuntimeError('boom')\n"
        "def after_all(ctx):\n"
        "    print('after_all')\n"
        "def on_failure(ctx):\n"
        "    print('on_failure')\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "workflow:\n"
        "  release:\n"
        "    script: release.py\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--config", str(config_file), "release", "patch", "--only", "prepare"])

    assert result.exit_code != 0
    assert "after_all" in result.output
    assert "on_failure" in result.output
