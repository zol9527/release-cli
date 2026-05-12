"""CLI 入口模块"""

from __future__ import annotations

import re
import sys
import shutil
import subprocess
import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import typer
import yaml
from packaging.version import InvalidVersion, Version

from .config import ReleaseConfig
from .filter import CommitFilter
from .packager import Packager
from .version import VersionManager, get_default_changelog_range, list_release_tags
from .workflow import WorkflowContext

app = typer.Typer(
    name="release",
    help="🚀 自动化发布工具 - 版本管理、变更生成、灵活打包",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


# 全局选项
_config_path: Optional[str] = None
RELEASE_FLOW_STEPS = {"preflight", "prepare", "commit", "pr"}
RELEASE_WORKFLOW_HOOKS = {
    "before_all",
    "after_all",
    "before_step",
    "after_step",
    "on_success",
    "on_failure",
}


def get_config() -> ReleaseConfig:
    """获取配置"""
    return ReleaseConfig(_config_path)


def get_template_dir() -> Path:
    """获取模板目录路径"""
    package_template_dir = Path(__file__).with_name("templates")
    if package_template_dir.exists():
        return package_template_dir

    return Path(__file__).parent.parent.parent / "templates"


def _resolve_versioned_changelog_path(output_dir: Path, changelog_date: str, version: str) -> Path:
    """根据日期和版本生成固定的 changelog 文件路径"""
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_version = version.removeprefix("v")
    return output_dir / f"{changelog_date}-v{normalized_version}.md"


def _normalize_changelog_date(value: str | None) -> str:
    """校验并标准化 changelog 日期"""
    if not value:
        return date.today().isoformat()

    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("--date 必须使用 YYYY-MM-DD 格式") from error

    normalized = parsed.isoformat()
    if normalized != value:
        raise ValueError("--date 必须使用 YYYY-MM-DD 格式")

    return normalized


def _render_changelog_markdown(
    version: str,
    title: str,
    released_at: str,
    from_ref: str | None,
    to_ref: str,
    commits: list[str],
    custom_notes: tuple[str, ...],
    commit_filter: CommitFilter,
) -> str:
    """使用固定格式渲染 changelog Markdown"""
    normalized_notes = [_normalize_note_item(item) for item in custom_notes if item.strip()]
    categories = commit_filter.categorize_commits(commits)
    lines = [
        "---",
        f'version: "{version.removeprefix("v")}"',
        f'title: "{_escape_yaml_string(title)}"',
        f'releasedAt: "{released_at}"',
        "pr: null",
        "prUrl: null",
        "---",
        "",
    ]

    section_specs = [
        ("新增功能", categories["features"]),
        ("问题修复", categories["fixes"] + categories["security"]),
        ("性能优化", categories["perf"]),
        ("重构改进", categories["refactor"]),
        ("其他变更", categories["other"]),
        ("自定义说明", normalized_notes),
    ]

    for title_text, items in section_specs:
        if not items:
            continue
        lines.append(f"## {title_text}")
        lines.append("")
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    lines.append(f"<!-- Range: {(from_ref + '..') if from_ref else ''}{to_ref} -->")
    lines.append("")
    return "\n".join(lines)


def _normalize_note_item(value: str) -> str:
    """将自定义 changelog 条目压缩为单行文本"""
    return " ".join(value.split())


def _escape_yaml_string(value: str) -> str:
    """转义 YAML 双引号字符串"""
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _render_monorepo_release_config(unit: str) -> str:
    """渲染 monorepo 发布单元配置"""
    return f"""# =============================================================================
# {unit} 发布单元配置
# =============================================================================

version:
  source: git-tag
  tag_prefix: "{unit}/v"
  file: _state/{unit}.VERSION
  hook: _shared/hooks/hook-version.py

changelog:
  root_dir: ../apps/{unit}
  output_dir: docs/changes

filter:
  ignore_messages:
    - "^docs:.*"
    - "^chore:.*"
    - "^style:.*"
    - ".*WIP.*"
    - ".*merge.*"
    - "^Revert.*"
  keep_types:
    - feat
    - fix
    - perf
    - refactor
    - security

release:
  steps:
    - preflight
    - prepare
    - commit
    - pr
  allowed_branches: []
  auto_stage: true
  commit_title: "🚀 release: {{tag}}"
  create_pr: false
  push: false
  base_branch: release
workflow:
  release:
    script: _shared/hooks/hook-release.py

packager:
  root_dir: ../apps/{unit}
  output_dir: release
  name: "{unit}-{{version}}"
  respect_gitignore: true
  include:
    - "*"
  exclude:
    - .git
    - .github
    - .beads
    - __pycache__
    - .venv
    - node_modules
    - dist
    - release
  force_include: []
"""


CHANGELOG_FILE_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-v(?P<version>.+)\.md$")


def _read_changelog_frontmatter(changelog_path: Path) -> dict[str, object]:
    """读取 changelog frontmatter"""
    content = changelog_path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"changelog 文件缺少 frontmatter: {changelog_path}")

    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        raise ValueError(f"changelog frontmatter 格式无效: {changelog_path}")

    try:
        frontmatter = yaml.safe_load(parts[0].removeprefix("---\n"))
    except yaml.YAMLError as error:
        raise ValueError(f"changelog frontmatter YAML 无法解析: {changelog_path}") from error

    if not isinstance(frontmatter, dict):
        raise ValueError(f"changelog frontmatter 格式无效: {changelog_path}")

    return frontmatter


def _resolve_latest_changelog_path(config: ReleaseConfig) -> Path:
    """定位最新的 changelog 文件"""
    changelog_dir = config.changelog_output_dir.resolve()
    if not changelog_dir.exists():
        raise ValueError("未找到 changelog 目录，请先执行 version --write")

    candidates = [path for path in changelog_dir.glob("*.md") if path.is_file() and CHANGELOG_FILE_RE.match(path.name)]
    if not candidates:
        raise ValueError("未找到 changelog 文件，请先执行 version --write")

    def sort_key(path: Path) -> tuple[date, Version, str]:
        match = CHANGELOG_FILE_RE.match(path.name)
        if not match:
            raise ValueError(f"无效的 changelog 文件名: {path}")

        try:
            changelog_date = date.fromisoformat(match.group("date"))
            changelog_version = Version(match.group("version"))
        except InvalidVersion as error:
            raise ValueError(f"changelog 文件名中的版本无效: {path}") from error
        except ValueError as error:
            raise ValueError(f"无效的 changelog 文件名: {path}") from error

        return (changelog_date, changelog_version, path.name)

    return max(candidates, key=sort_key)


def _resolve_pack_version(config: ReleaseConfig) -> tuple[str, Path]:
    """从最新 changelog 中解析打包版本"""
    changelog_path = _resolve_latest_changelog_path(config)
    frontmatter = _read_changelog_frontmatter(changelog_path)
    version = frontmatter.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"最新 changelog 未声明有效 version: {changelog_path}")

    vm = VersionManager(config)
    normalized_version = version.strip()
    if normalized_version in vm.VERSION_TYPES:
        raise ValueError(f"最新 changelog 的 version 必须是明确版本号，不能是 {normalized_version!r}: {changelog_path}")

    return vm.resolve_version(normalized_version), changelog_path


def _resolve_written_release_version(config: ReleaseConfig) -> str:
    """读取 version 阶段已写出的发布版本号"""
    vm = VersionManager(config)
    version_file = config.version_file
    if not version_file.exists():
        raise ValueError("未找到版本文件，请先执行 version --write")

    content = version_file.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError("版本文件为空，请先执行 version --write")

    return vm.resolve_version(content)


def _build_released_at(changelog_date: str) -> str:
    """构造 changelog releasedAt 字段"""
    current_utc = datetime.now(timezone.utc)
    released_at = datetime.combine(
        date.fromisoformat(changelog_date),
        current_utc.timetz().replace(tzinfo=None),
        tzinfo=timezone.utc,
    )
    return released_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _build_release_commit_message(config: ReleaseConfig, version: str) -> str:
    """构造发布提交信息"""
    normalized_version = version.removeprefix("v")
    tag = _build_release_tag(config, normalized_version)
    try:
        message = config.release_commit_title.format(
            version=normalized_version,
            tag=tag,
            tag_prefix=config.version_tag_prefix,
        )
        return message.strip() or "🚀 release: {tag}".format(tag=tag)
    except KeyError as error:
        raise ValueError(f"release.commit_title 使用了不支持的变量: {{{error.args[0]}}}") from error
    except ValueError as error:
        raise ValueError(f"release.commit_title 模板格式无效: {error}") from error


def _build_release_tag(config: ReleaseConfig, version: str) -> str:
    """构造发布标签名"""
    return f"{config.version_tag_prefix}{version.removeprefix('v')}"


def _parse_csv_steps(value: str | None) -> list[str]:
    """解析逗号分隔的流水线步骤名"""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate_release_steps(steps: list[str]) -> None:
    """校验发布流水线步骤是否受支持"""
    invalid = [step for step in steps if step not in RELEASE_FLOW_STEPS]
    if invalid:
        raise ValueError(f"不支持的 release 步骤: {', '.join(invalid)}")


def _select_release_steps(
    configured_steps: list[str],
    *,
    from_step: str | None,
    to_step: str | None,
    only_steps: list[str],
    skip_steps: list[str],
    no_commit: bool,
) -> list[str]:
    """根据运行时选项筛选本次需要执行的 release 步骤"""
    steps = list(configured_steps)
    _validate_release_steps(steps)

    if no_commit:
        steps = [step for step in steps if step not in {"commit", "pr"}]

    selectors = [step for step in [from_step, to_step, *only_steps, *skip_steps] if step]
    _validate_release_steps(selectors)

    if only_steps:
        return [step for step in steps if step in set(only_steps)]

    if from_step:
        start_index = steps.index(from_step)
        steps = steps[start_index:]
    if to_step:
        end_index = steps.index(to_step)
        steps = steps[: end_index + 1]
    if skip_steps:
        steps = [step for step in steps if step not in set(skip_steps)]

    return steps


def _git_output_checked(cwd: Path, args: list[str]) -> str:
    """执行 git 命令并返回 stdout"""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_root(cwd: Path) -> Path:
    """获取 Git 仓库根目录"""
    output = _git_output_checked(cwd, ["rev-parse", "--show-toplevel"])
    return Path(output).resolve()


def _current_branch(cwd: Path) -> str:
    """获取当前分支名"""
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "-q", "HEAD"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _release_preflight(
    config: ReleaseConfig,
    *,
    target_version: str,
    from_ref: str | None,
    allow_dirty: bool,
    create_pr: bool,
) -> None:
    """执行 release 前置检查"""
    missing = [command for command in ["git"] if shutil.which(command) is None]
    if create_pr and shutil.which("gh") is None:
        missing.append("gh")
    if missing:
        raise ValueError(f"缺少必要命令: {' '.join(missing)}")

    cwd = _git_root(config.packager_root_dir)
    branch = _current_branch(cwd)
    if not branch:
        raise ValueError("当前处于 detached HEAD，无法安全执行发布")

    allowed_patterns = config.release_allowed_branches
    if allowed_patterns and not any(re.fullmatch(pattern, branch) for pattern in allowed_patterns):
        raise ValueError(f"当前分支 {branch} 不允许执行发布，允许模式: {', '.join(allowed_patterns)}")

    dirty = _git_output_checked(cwd, ["status", "--short"])
    if dirty and not allow_dirty:
        # 首发时（无 release tag），允许 VERSION 文件有未提交变更
        has_release_tags = bool(list_release_tags(cwd, ["--merged", "HEAD"], config.version_tag_prefix))
        if not has_release_tags:
            version_file_relative = _try_relative_path(config.version_file, cwd)
            dirty_lines = [line for line in dirty.splitlines()
                           if version_file_relative not in line]
            if not dirty_lines:
                typer.echo(f"ℹ️  首发模式：允许 VERSION 文件存在未提交变更")
            else:
                raise ValueError(
                    f"工作区存在未提交变更（不含 VERSION 文件），请先清理:\n"
                    + "\n".join(f"  {line}" for line in dirty_lines)
                )
        else:
            raise ValueError("工作区存在未提交变更，请先清理，或传入 --allow-dirty")

    tag_name = _build_release_tag(config, target_version)
    existing_tag = _git_output_checked(cwd, ["tag", "--list", tag_name])
    if existing_tag:
        raise ValueError(f"目标 Git Tag 已存在: {tag_name}")

    if from_ref:
        commit_count = _git_output_checked(cwd, ["rev-list", "--count", f"{from_ref}..HEAD"])
        if commit_count == "0":
            raise ValueError(f"从 {from_ref} 到 HEAD 没有新的提交，无法生成发布")

    typer.echo(f"📌 当前分支: {branch}")
    typer.echo(f"🎯 目标版本: {tag_name}")
    typer.echo(f"🧭 变更起点: {from_ref or '仓库首个提交'}")


def _write_release_version(
    config: ReleaseConfig,
    *,
    target_version: str,
    from_ref: str | None,
    changelog_date: str | None,
    title: str,
    notes: tuple[str, ...],
    show_all: bool,
    dry_run: bool,
) -> Path | None:
    """执行 prepare 阶段：生成 changelog、写入版本并执行 version hook"""
    if dry_run:
        typer.echo(f"🧪 DRY RUN: 将生成版本 {target_version}")
        return None

    changelog_path, changelog_markdown, commit_count = _prepare_changelog(
        config,
        version=target_version,
        from_ref=from_ref,
        changelog_date=changelog_date,
        title=title,
        notes=notes,
        show_all=show_all,
    )
    changelog_existed = changelog_path.exists()
    previous_changelog = changelog_path.read_text(encoding="utf-8") if changelog_existed else None
    changelog_path.write_text(changelog_markdown, encoding="utf-8")

    try:
        VersionManager(config).write_version(target_version)
    except Exception:
        if changelog_existed and previous_changelog is not None:
            changelog_path.write_text(previous_changelog, encoding="utf-8")
        elif changelog_path.exists():
            changelog_path.unlink()
        raise

    typer.echo(f"✅ 已写入版本: {target_version}")
    typer.echo(f"📝 已更新版本文件: {config.version_file}")
    typer.echo(f"📝 已生成 changelog: {changelog_path}")
    typer.echo(f"📋 changelog 提交条目: {commit_count}，自定义条目: {len(notes)}")
    return changelog_path


def _release_stage_paths(config: ReleaseConfig, changelog_path: Path) -> list[Path]:
    """收集 release commit 阶段需要暂存的路径"""
    paths = [config.version_file, changelog_path]
    package_json = config.packager_root_dir / "package.json"
    manifest_json = config.packager_root_dir / "src" / "manifest.json"
    if package_json.exists():
        paths.append(package_json)
    if manifest_json.exists():
        paths.append(manifest_json)

    for item in config.release_config.get("stage_paths", []):
        paths.append(config.resolve_project_path(str(item)))

    return paths


def _release_commit_step(config: ReleaseConfig, changelog_path: Path | None, dry_run: bool) -> None:
    """执行 commit 阶段：暂存发布文件、提交并创建 tag"""
    if dry_run:
        typer.echo("🧪 DRY RUN: 将提交发布文件并创建 Git tag")
        return
    if changelog_path is None:
        changelog_path = _resolve_latest_changelog_path(config)

    cwd = _git_root(config.packager_root_dir)
    if config.release_auto_stage:
        paths = [str(path) for path in _release_stage_paths(config, changelog_path)]
        subprocess.run(["git", "add", "--", *paths], cwd=cwd, check=True)

    status = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    staged_files = {
        (cwd / relative_path).resolve()
        for relative_path in status.stdout.splitlines()
        if relative_path.strip()
    }
    version, checked_changelog_path, resolved_date = _ensure_release_files_ready(config, staged_files, cwd)
    message = _build_release_commit_message(config, version)
    tag_name = _build_release_tag(config, version)

    if _git_ref_exists(cwd, f"refs/tags/{tag_name}"):
        raise ValueError(f"Git Tag 已存在: {tag_name}")

    subprocess.run(["git", "commit", "-m", message], cwd=cwd, check=True)
    subprocess.run(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"], cwd=cwd, check=True)
    typer.echo(f"✅ 已创建提交: {message}")
    typer.echo(f"🏷️ 已创建 Git Tag: {tag_name}")
    typer.echo(f"📝 已校验版本文件与 changelog: {checked_changelog_path} ({resolved_date})")


def _release_pr_step(config: ReleaseConfig, create_pr: bool, push: bool, dry_run: bool) -> None:
    """执行 PR 阶段"""
    if not create_pr:
        typer.echo("⏭️  默认不自动创建 PR；如需创建，请传入 --create-pr 或配置 release.create_pr")
        return

    cwd = _git_root(config.packager_root_dir)
    branch = _current_branch(cwd)
    version = _resolve_written_release_version(config)
    title = f"🔧 chore(release): 准备 {_build_release_tag(config, version)} 发布"
    body = (
        "## 发布信息\n"
        f"- 目标版本: {_build_release_tag(config, version)}\n"
        f"- 来源分支: {branch}\n\n"
        "## 说明\n"
        "- 该 PR 由 `release-cli release` 自动创建。\n"
        "- 请在合并前确认 changelog 与版本号是否正确。\n"
    )

    if dry_run:
        typer.echo(f"🧪 DRY RUN: 将创建到 {config.release_base_branch} 的发布 PR")
        return
    if push:
        subprocess.run(["git", "push", "origin", branch], cwd=cwd, check=True)
    subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            config.release_base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=cwd,
        check=True,
    )
    typer.echo(f"✅ 已创建到 {config.release_base_branch} 的发布 PR")


def _load_workflow_steps(script_path: Path) -> dict[str, object]:
    """加载用户自定义 workflow 脚本中的 @step 函数"""
    if not script_path.is_file():
        raise ValueError(f"workflow 脚本不存在: {script_path}")

    module_name = f"release_cli_user_workflow_{abs(hash(script_path))}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"无法加载 workflow 脚本: {script_path}")

    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode

    steps: dict[str, object] = {}
    for name, value in vars(module).items():
        if callable(value) and (getattr(value, "__release_cli_step__", False) or _is_workflow_function_name(name)):
            steps[name] = value
    return steps


def _is_workflow_function_name(name: str) -> bool:
    """判断函数名是否是 release workflow 约定名称"""
    return name in RELEASE_FLOW_STEPS or name in RELEASE_WORKFLOW_HOOKS


def _run_custom_release_workflow(
    config: ReleaseConfig,
    *,
    script_path: Path,
    selected_steps: list[str],
    target_version: str,
    resolved_from_ref: str | None,
    changelog_date: str | None,
    title: str,
    notes: tuple[str, ...],
    show_all: bool,
    dry_run: bool,
    allow_dirty: bool,
    create_pr: bool,
    push: bool,
) -> None:
    """执行用户自定义 Python release workflow"""
    workflow_steps = _load_workflow_steps(script_path)

    changelog_path: Path | None = None

    def run_builtin(step_name: str) -> None:
        nonlocal changelog_path
        if step_name == "preflight":
            _release_preflight(
                config,
                target_version=target_version,
                from_ref=resolved_from_ref,
                allow_dirty=allow_dirty,
                create_pr=create_pr,
            )
        elif step_name == "prepare":
            changelog_path = _write_release_version(
                config,
                target_version=target_version,
                from_ref=resolved_from_ref,
                changelog_date=changelog_date,
                title=title,
                notes=notes,
                show_all=show_all,
                dry_run=dry_run,
            )
        elif step_name == "commit":
            _release_commit_step(config, changelog_path, dry_run)
        elif step_name == "pr":
            _release_pr_step(config, create_pr, push, dry_run)
        else:
            raise ValueError(f"不支持的内置 release 步骤: {step_name}")

    def make_ctx(step_name: str) -> WorkflowContext:
        return WorkflowContext(
            config=config,
            version=target_version,
            tag=_build_release_tag(config, target_version),
            step=step_name,
            dry_run=dry_run,
            builtin_runner=run_builtin,
        )

    def run_workflow_func(name: str, ctx: WorkflowContext) -> None:
        workflow_func = workflow_steps.get(name)
        if workflow_func is not None:
            workflow_func(ctx)  # type: ignore[operator]

    typer.echo(f"🐍 Workflow Script: {script_path}")
    try:
        run_workflow_func("before_all", make_ctx("before_all"))
        for step_name in selected_steps:
            workflow_step = workflow_steps.get(step_name)
            if workflow_step is None:
                typer.echo("")
                typer.echo(f"⏭️  [{step_name}] workflow 未定义，跳过")
                continue

            typer.echo("")
            typer.echo(f"▶️  [{step_name}]")
            ctx = make_ctx(step_name)
            run_workflow_func("before_step", ctx)
            workflow_step(ctx)  # type: ignore[operator]
            run_workflow_func("after_step", ctx)
            typer.echo(f"✅ [{step_name}] 完成")
    except Exception:
        run_workflow_func("after_all", make_ctx("after_all"))
        run_workflow_func("on_failure", make_ctx("on_failure"))
        raise
    else:
        run_workflow_func("after_all", make_ctx("after_all"))
        run_workflow_func("on_success", make_ctx("on_success"))


def _prepare_changelog(
    config: ReleaseConfig,
    *,
    version: str,
    from_ref: str | None,
    changelog_date: str | None,
    title: str,
    notes: tuple[str, ...],
    show_all: bool,
) -> tuple[Path, str, int]:
    """预计算 changelog 内容，直到最终写盘前都不修改文件"""
    commit_filter = CommitFilter(config)
    normalized_date = _normalize_changelog_date(changelog_date)

    to_ref = "HEAD"
    resolved_from_ref = from_ref
    if not resolved_from_ref:
        resolved_from_ref, to_ref = get_default_changelog_range(
            config.packager_root_dir,
            config.version_tag_prefix,
        )

    revision_range = f"{resolved_from_ref}..{to_ref}" if resolved_from_ref else to_ref
    result = subprocess.run(
        ["git", "log", revision_range, "--pretty=format:%s", "--no-merges"],
        capture_output=True,
        text=True,
        check=True,
        cwd=config.packager_root_dir,
    )

    commits = [commit for commit in result.stdout.splitlines() if commit.strip()]
    filtered_commits = commits if show_all else commit_filter.filter_commits(commits)
    released_at = _build_released_at(normalized_date)
    markdown = _render_changelog_markdown(
        version,
        title,
        released_at,
        resolved_from_ref,
        to_ref,
        filtered_commits,
        notes,
        commit_filter,
    )
    output_path = _resolve_versioned_changelog_path(config.changelog_output_dir, normalized_date, version)
    return output_path, markdown, len(filtered_commits)


def _git_ref_exists(cwd: Path, ref: str) -> bool:
    """检查 Git 引用是否已存在"""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _try_relative_path(path: Path, base: Path) -> str:
    """尝试将路径转为相对路径，失败则返回绝对路径字符串"""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _ensure_release_files_ready(
    config: ReleaseConfig,
    staged_files: set[Path],
    cwd: Path,
) -> tuple[str, Path, str]:
    """校验发布文件是否齐全且已纳入本次提交

    首发场景下（无 release tag），如果 VERSION 文件内容已经与目标版本一致
    但未被 staged（git add 不会 stage 内容相同的文件），视为通过。
    """
    version_file = config.version_file.resolve()
    normalized_version = _resolve_written_release_version(config)

    changelog_dir = config.changelog_output_dir.resolve()
    candidates = sorted(changelog_dir.glob(f"*-v{normalized_version}.md"))
    if not candidates:
        raise ValueError(f"未找到版本 v{normalized_version} 对应的 changelog 文件，请先执行 version --write")
    if len(candidates) > 1:
        raise ValueError("检测到多个同版本 changelog 文件，请回到 version 阶段重新生成并确保仅保留一个目标 changelog")
    changelog_path = candidates[0].resolve()
    normalized_date = changelog_path.stem[:10]

    frontmatter = _read_changelog_frontmatter(changelog_path)
    changelog_version = frontmatter.get("version")
    if not isinstance(changelog_version, str) or not changelog_version.strip():
        raise ValueError(f"changelog 未声明有效 version: {changelog_path}")

    normalized_changelog_version = VersionManager(config).resolve_version(changelog_version.strip())
    if normalized_changelog_version != normalized_version:
        raise ValueError(
            f"changelog 中的版本为 v{normalized_changelog_version}，与版本文件中的 v{normalized_version} 不一致"
        )

    # 首发时检查：无 release tag 则允许 VERSION 文件内容已正确但未 staged
    is_first_release = not bool(list_release_tags(cwd, ["--merged", "HEAD"], config.version_tag_prefix))

    missing = []
    for path in (version_file, changelog_path):
        if path in staged_files:
            continue
        # 首发时：VERSION 文件内容已正确 → 放行
        if is_first_release and path == version_file:
            if path.exists():
                content = path.read_text(encoding="utf-8").strip().removeprefix("v")
                if content == normalized_version:
                    typer.echo(f"ℹ️  首发模式：{path.name} 内容已正确但未暂存，视为通过")
                    continue
        missing.append(path)

    if missing:
        missing_names = "\n".join(f"- {path}" for path in sorted(missing))
        raise ValueError(f"以下发布文件尚未纳入本次提交:\n{missing_names}")

    unstaged = subprocess.run(
        ["git", "diff", "--name-only", "--", str(version_file), str(changelog_path)],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    if unstaged.stdout.strip():
        raise ValueError("版本文件或 changelog 存在未暂存改动，请先整理后再提交")

    return normalized_version, changelog_path, normalized_date


@app.callback()
def callback(
    config: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="配置文件路径",
        envvar="RELEASE_CONFIG",
    ),
) -> None:
    """全局选项"""
    global _config_path
    _config_path = config


@app.command()
def init(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="强制覆盖已存在的配置文件",
    ),
    monorepo: bool = typer.Option(
        False,
        "--monorepo",
        help="生成 monorepo 多发布单元配置",
    ),
    units: Optional[str] = typer.Option(
        None,
        "--units",
        help="monorepo 发布单元列表，逗号分隔，例如 backend,wechat",
    ),
) -> None:
    """初始化发布配置"""
    template_dir = get_template_dir()
    if not template_dir.exists():
        typer.echo("❌ 未找到内置模板目录", err=True)
        raise typer.Exit(1)

    if monorepo:
        unit_names = _parse_csv_steps(units)
        if not unit_names:
            typer.echo("❌ --monorepo 需要传入 --units，例如 --units backend,wechat", err=True)
            raise typer.Exit(1)

        release_dir = Path(".release")
        shared_dir = release_dir / "_shared"
        generated_targets = [release_dir / f"{unit}.yml" for unit in unit_names]
        generated_targets.extend(
            [
                shared_dir / "hooks" / "hook-version.py",
                shared_dir / "hooks" / "hook-release.py",
                *(release_dir / "_state" / f"{unit}.VERSION" for unit in unit_names),
            ]
        )
        existing_targets = [target for target in generated_targets if target.exists()]
        if existing_targets and not force:
            typer.echo("❌ 以下文件已存在，使用 --force 覆盖:", err=True)
            for target in existing_targets:
                typer.echo(f"  - {target}", err=True)
            raise typer.Exit(1)

        release_dir.mkdir(parents=True, exist_ok=True)
        for unit in unit_names:
            target = release_dir / f"{unit}.yml"
            target.write_text(_render_monorepo_release_config(unit), encoding="utf-8")
            typer.echo(f"✅ 已生成发布单元配置: {target}")

            version_target = release_dir / "_state" / f"{unit}.VERSION"
            version_target.parent.mkdir(parents=True, exist_ok=True)
            version_target.write_text("v0.1.0\n", encoding="utf-8")
            typer.echo(f"✅ 已生成发布单元版本文件: {version_target}")

        hook_template = template_dir / "hooks" / "hook-version.py"
        if hook_template.exists():
            hook_target = shared_dir / "hooks" / "hook-version.py"
            hook_target.parent.mkdir(parents=True, exist_ok=True)
            hook_target.write_text(hook_template.read_text(encoding="utf-8"), encoding="utf-8")
            typer.echo(f"✅ 已生成共享版本 Hook: {hook_target}")

        workflow_template = template_dir / "hooks" / "hook-release.py"
        if workflow_template.exists():
            workflow_target = shared_dir / "hooks" / "hook-release.py"
            workflow_target.parent.mkdir(parents=True, exist_ok=True)
            workflow_target.write_text(workflow_template.read_text(encoding="utf-8"), encoding="utf-8")
            typer.echo(f"✅ 已生成共享 Release Workflow: {workflow_target}")
        return

    release_dir = Path(".release")
    shared_dir = release_dir / "_shared"
    config_file = release_dir / "release.yml"
    version_file = release_dir / "_state" / "VERSION"
    hook_file = shared_dir / "hooks" / "hook-version.py"
    workflow_file = shared_dir / "hooks" / "hook-release.py"
    github_dir = Path(".github/workflows")
    github_template_dir = template_dir / "github"

    generated_targets = [config_file, version_file, hook_file, workflow_file]
    if github_template_dir.exists():
        generated_targets.extend(github_dir / template_file.name for template_file in github_template_dir.glob("*.yml"))

    existing_targets = [target for target in generated_targets if target.exists()]
    if existing_targets and not force:
        typer.echo("❌ 以下文件已存在，使用 --force 覆盖:", err=True)
        for target in existing_targets:
            typer.echo(f"  - {target}", err=True)
        raise typer.Exit(1)

    config_template = template_dir / ".release.yml"
    if config_template.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(config_template.read_text(encoding="utf-8"), encoding="utf-8")
        typer.echo(f"✅ 已生成配置文件: {config_file}")

    version_template = template_dir / "VERSION"
    if version_template.exists() and version_template.read_text(encoding="utf-8").strip():
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(version_template.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text("v0.1.0\n", encoding="utf-8")
    typer.echo(f"✅ 已生成版本文件: {version_file}")

    hook_template = template_dir / "hooks" / "hook-version.py"
    if hook_template.exists():
        hook_file.parent.mkdir(parents=True, exist_ok=True)
        hook_file.write_text(hook_template.read_text(encoding="utf-8"), encoding="utf-8")
        typer.echo(f"✅ 已生成版本 Hook 示例: {hook_file}")

    workflow_template = template_dir / "hooks" / "hook-release.py"
    if workflow_template.exists():
        workflow_file.parent.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text(workflow_template.read_text(encoding="utf-8"), encoding="utf-8")
        typer.echo(f"✅ 已生成 Release Workflow 模板: {workflow_file}")

    github_dir.mkdir(parents=True, exist_ok=True)
    if github_template_dir.exists():
        for template_file in github_template_dir.glob("*.yml"):
            target_file = github_dir / template_file.name
            target_file.write_text(template_file.read_text(encoding="utf-8"), encoding="utf-8")
            typer.echo(f"✅ 已生成 GitHub Actions: {target_file}")


@app.command()
def version(
    value: str = typer.Argument(
        ...,
        help="版本类型或明确版本号，例如 patch 或 1.2.3",
    ),
    write: bool = typer.Option(
        False,
        "--write",
        "-w",
        help="写入版本文件，并同步生成 changelog；如果配置了 hook，会在写入后执行",
    ),
    from_ref: Optional[str] = typer.Option(
        None,
        "--from",
        "-f",
        help="生成 changelog 时使用的起始 ref，不指定则自动推导最近发布区间",
    ),
    changelog_date: Optional[str] = typer.Option(
        None,
        "--date",
        help="生成 changelog 的日期，默认使用当天，格式 YYYY-MM-DD",
    ),
    title: str = typer.Option(
        "发布新版本",
        "--title",
        help="自动生成 changelog 时使用的标题",
    ),
    note: list[str] = typer.Option(
        [],
        "--note",
        "-n",
        help="自动生成 changelog 时附带的自定义条目，可重复传入",
    ),
    show_all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="自动生成 changelog 时显示所有提交，不套用 filter 规则",
    ),
) -> None:
    """计算或写入版本号"""
    try:
        config = get_config()
        vm = VersionManager(config)

        target_version = vm.resolve_version(value)

        if write:
            changelog_path, changelog_markdown, commit_count = _prepare_changelog(
                config,
                version=target_version,
                from_ref=from_ref,
                changelog_date=changelog_date,
                title=title,
                notes=tuple(note),
                show_all=show_all,
            )
            changelog_existed = changelog_path.exists()
            previous_changelog = changelog_path.read_text(encoding="utf-8") if changelog_existed else None
            changelog_path.write_text(changelog_markdown, encoding="utf-8")

            try:
                vm.write_version(target_version)
            except Exception:
                if changelog_existed and previous_changelog is not None:
                    changelog_path.write_text(previous_changelog, encoding="utf-8")
                elif changelog_path.exists():
                    changelog_path.unlink()
                raise

            typer.echo(f"✅ 已写入版本: {target_version}")
            typer.echo(f"📝 已更新版本文件: {config.version_file}")
            typer.echo(f"📝 已生成 changelog: {changelog_path}")
            typer.echo(f"📋 changelog 提交条目: {commit_count}，自定义条目: {len(note)}")

            if config.version_hook:
                typer.echo(f"🪝 已执行版本 Hook: {config.version_hook}")
        else:
            current = vm.get_current_version()
            if current == target_version:
                typer.echo(f"{target_version} (当前版本)")
            else:
                typer.echo(f"{target_version} (当前: {current})")
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() if error.stderr else str(error)
        typer.echo(f"❌ {message}", err=True)
        raise typer.Exit(1) from error
    except ValueError as error:
        typer.echo(f"❌ {error}", err=True)
        raise typer.Exit(1) from error


@app.command("commit")
def commit_cmd(
    stage_all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="提交前先执行 git add -A",
    ),
) -> None:
    """生成发布提交"""
    try:
        config = get_config()
        cwd = _git_root(config.packager_root_dir)

        if stage_all:
            subprocess.run(["git", "add", "-A"], check=True, cwd=cwd)

        status = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if not status.stdout.strip():
            raise ValueError("没有已暂存的变更，可先手动 git add 或使用 release-cli commit --all")

        staged_files = {
            (cwd / relative_path).resolve()
            for relative_path in status.stdout.splitlines()
            if relative_path.strip()
        }
        version, changelog_path, resolved_date = _ensure_release_files_ready(config, staged_files, cwd)
        message = _build_release_commit_message(config, version)
        tag_name = _build_release_tag(config, version)

        if _git_ref_exists(cwd, f"refs/tags/{tag_name}"):
            raise ValueError(f"Git Tag 已存在: {tag_name}")

        subprocess.run(["git", "commit", "-m", message], check=True, cwd=cwd)
        subprocess.run(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"], check=True, cwd=cwd)
        typer.echo(f"✅ 已创建提交: {message}")
        typer.echo(f"🏷️ 已创建 Git Tag: {tag_name}")
        typer.echo(f"📝 已校验版本文件与 changelog: {changelog_path} ({resolved_date})")
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() if error.stderr else str(error)
        typer.echo(f"❌ {message}", err=True)
        raise typer.Exit(1) from error
    except ValueError as error:
        typer.echo(f"❌ {error}", err=True)
        raise typer.Exit(1) from error


@app.command("release")
def release_cmd(
    value: str = typer.Argument(
        "patch",
        help="版本类型或明确版本号，例如 patch、minor、major 或 1.2.3",
    ),
    from_step: Optional[str] = typer.Option(
        None,
        "--from-step",
        help="从指定步骤开始执行，例如 prepare",
    ),
    to_step: Optional[str] = typer.Option(
        None,
        "--to-step",
        help="执行到指定步骤后停止，例如 prepare",
    ),
    only: Optional[str] = typer.Option(
        None,
        "--only",
        help="只执行指定步骤，多个步骤用逗号分隔",
    ),
    skip: Optional[str] = typer.Option(
        None,
        "--skip",
        help="跳过指定步骤，多个步骤用逗号分隔",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="只打印将要执行的步骤，不写文件、不提交",
    ),
    allow_dirty: bool = typer.Option(
        False,
        "--allow-dirty",
        help="允许在工作区存在未提交变更时执行",
    ),
    no_commit: bool = typer.Option(
        False,
        "--no-commit",
        help="只生成版本文件和 changelog，不执行 commit/pr",
    ),
    create_pr: bool = typer.Option(
        False,
        "--create-pr",
        help="执行 PR 创建步骤",
    ),
    push: bool = typer.Option(
        False,
        "--push",
        help="创建 PR 前推送当前分支",
    ),
    from_ref: Optional[str] = typer.Option(
        None,
        "--from",
        "-f",
        help="生成 changelog 时使用的起始 ref",
    ),
    changelog_date: Optional[str] = typer.Option(
        None,
        "--date",
        help="生成 changelog 的日期，格式 YYYY-MM-DD",
    ),
    title: str = typer.Option(
        "发布新版本",
        "--title",
        help="自动生成 changelog 时使用的标题",
    ),
    note: list[str] = typer.Option(
        [],
        "--note",
        "-n",
        help="自动生成 changelog 时附带的自定义条目，可重复传入",
    ),
    show_all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="自动生成 changelog 时显示所有提交，不套用 filter 规则",
    ),
) -> None:
    """按 preflight/prepare/commit/pr 阶段执行完整发布流水线"""
    try:
        config = get_config()
        vm = VersionManager(config)
        target_version = vm.resolve_version(value)
        selected_steps = _select_release_steps(
            config.release_steps,
            from_step=from_step,
            to_step=to_step,
            only_steps=_parse_csv_steps(only),
            skip_steps=_parse_csv_steps(skip),
            no_commit=no_commit,
        )
        effective_create_pr = create_pr or config.release_create_pr
        effective_push = push or config.release_push
        resolved_from_ref = from_ref
        if resolved_from_ref is None:
            resolved_from_ref, _ = get_default_changelog_range(
                config.packager_root_dir,
                config.version_tag_prefix,
            )

        typer.echo(f"🚀 Release Flow: {config.config_path}")
        typer.echo(f"📋 Steps: {' -> '.join(selected_steps)}")

        workflow_script = config.workflow_script("release")
        if workflow_script is not None:
            _run_custom_release_workflow(
                config,
                script_path=workflow_script,
                selected_steps=selected_steps,
                target_version=target_version,
                resolved_from_ref=resolved_from_ref,
                changelog_date=changelog_date,
                title=title,
                notes=tuple(note),
                show_all=show_all,
                dry_run=dry_run,
                allow_dirty=allow_dirty,
                create_pr=effective_create_pr,
                push=effective_push,
            )
            typer.echo("")
            typer.echo("🏁 Release Flow 完成")
            return

        changelog_path: Path | None = None

        for step in selected_steps:
            typer.echo("")
            typer.echo(f"▶️  [{step}]")

            if step == "preflight":
                _release_preflight(
                    config,
                    target_version=target_version,
                    from_ref=resolved_from_ref,
                    allow_dirty=allow_dirty,
                    create_pr=effective_create_pr,
                )
            elif step == "prepare":
                changelog_path = _write_release_version(
                    config,
                    target_version=target_version,
                    from_ref=resolved_from_ref,
                    changelog_date=changelog_date,
                    title=title,
                    notes=tuple(note),
                    show_all=show_all,
                    dry_run=dry_run,
                )
            elif step == "commit":
                _release_commit_step(config, changelog_path, dry_run)
            elif step == "pr":
                _release_pr_step(config, effective_create_pr, effective_push, dry_run)

            typer.echo(f"✅ [{step}] 完成")

        typer.echo("")
        typer.echo("🏁 Release Flow 完成")
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() if error.stderr else str(error)
        typer.echo(f"❌ {message}", err=True)
        raise typer.Exit(error.returncode or 1) from error
    except ValueError as error:
        typer.echo(f"❌ {error}", err=True)
        raise typer.Exit(1) from error


@app.command()
def pack(
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="输出目录，默认使用 packager.output_dir",
    ),
) -> None:
    """创建安装包"""
    config = get_config()

    try:
        version, changelog_path = _resolve_pack_version(config)
        packager = Packager(config)
        output_dir = Path(output) if output else None
        output_path = packager.create_package(version, output_dir)

        typer.echo(f"✅ 已创建安装包: {output_path}")
        typer.echo(f"📝 版本来源: {changelog_path}")
        typer.echo(f"📦 包名: {packager.get_package_name(version)}")
        typer.echo(f"📏 大小: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
    except ValueError as error:
        typer.echo(f"❌ {error}", err=True)
        raise typer.Exit(1) from error


if __name__ == "__main__":
    app()
