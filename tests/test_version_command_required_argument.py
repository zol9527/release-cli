from __future__ import annotations

from typer.testing import CliRunner

from release_cli.cli import app

runner = CliRunner()


def test_version_command_requires_value_argument() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code != 0
    assert "Missing argument 'VALUE'" in result.output


def test_version_command_accepts_explicit_patch_argument() -> None:
    result = runner.invoke(app, ["version", "patch"])

    assert result.exit_code == 0
    assert "0.0.1" in result.output


def test_root_command_supports_short_help_option() -> None:
    result = runner.invoke(app, ["-h"])

    assert result.exit_code == 0
    assert "自动化发布工具" in result.output
    assert "version" in result.output
