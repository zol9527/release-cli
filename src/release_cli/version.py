"""版本管理模块"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import ReleaseConfig

RELEASE_TAG_PATTERN = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def _git_output(cwd: Path, args: list[str]) -> str | None:
    """执行 git 命令并返回标准输出"""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
    except subprocess.CalledProcessError:
        return None

    output = result.stdout.strip()
    return output or None


def _parse_prerelease_identifier(value: str) -> tuple[int, int | str]:
    """将 prerelease 标识转换为可排序结构"""
    if value.isdigit():
        return (0, int(value))
    return (1, value)


def _strip_tag_prefix(tag: str, tag_prefix: str) -> str | None:
    """移除发布 tag 前缀, 返回可解析的 semver 部分"""
    if tag_prefix and tag.startswith(tag_prefix):
        return tag.removeprefix(tag_prefix)

    # 兼容旧项目: 默认 v 前缀下继续接受没有 v 的历史 tag。
    if tag_prefix == "v" and RELEASE_TAG_PATTERN.match(tag):
        return tag.removeprefix("v")

    return None


def _semver_sort_key(tag: str, tag_prefix: str = "v") -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
    """生成 semver 排序键, build metadata 不参与优先级比较"""
    version_part = _strip_tag_prefix(tag, tag_prefix)
    if version_part is None:
        return (0, 0, 0, 0, ())

    match = RELEASE_TAG_PATTERN.match(version_part)
    if not match:
        return (0, 0, 0, 0, ())

    prerelease = match.group("prerelease")
    prerelease_key: tuple[tuple[int, int | str], ...] = ()
    if prerelease:
        prerelease_key = tuple(_parse_prerelease_identifier(part) for part in prerelease.split("."))

    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        0 if prerelease else 1,
        prerelease_key,
    )


def list_release_tags(cwd: Path, args: list[str], tag_prefix: str = "v") -> list[str]:
    """列出符合语义化版本规则的 Git tag, 并按版本倒序排序"""
    output = _git_output(cwd, ["tag", *args])
    if not output:
        return []

    tags = [
        tag.strip()
        for tag in output.splitlines()
        if tag.strip()
        and (version_part := _strip_tag_prefix(tag.strip(), tag_prefix)) is not None
        and RELEASE_TAG_PATTERN.match(version_part)
    ]
    return sorted(tags, key=lambda tag: _semver_sort_key(tag, tag_prefix), reverse=True)


def get_tag_commit(cwd: Path, tag: str) -> str | None:
    """获取 tag 对应的提交 SHA"""
    return _git_output(cwd, ["rev-list", "-n", "1", tag])


def get_head_release_tag(cwd: Path, tag_prefix: str = "v") -> str | None:
    """获取当前 HEAD 上最高优先级的发布 tag"""
    tags = list_release_tags(cwd, ["--points-at", "HEAD"], tag_prefix)
    return tags[0] if tags else None


def get_current_release_tag(cwd: Path, tag_prefix: str = "v") -> str | None:
    """获取当前发布线上的最新发布 tag"""
    head_tag = get_head_release_tag(cwd, tag_prefix)
    if head_tag:
        return head_tag

    merged_tags = list_release_tags(cwd, ["--merged", "HEAD"], tag_prefix)
    return merged_tags[0] if merged_tags else None


def get_default_changelog_range(cwd: Path, tag_prefix: str = "v") -> tuple[str | None, str]:
    """根据发布 tag 自动推导 changelog 默认区间"""
    merged_tags = list_release_tags(cwd, ["--merged", "HEAD"], tag_prefix)
    head_tag = get_head_release_tag(cwd, tag_prefix)
    if head_tag:
        head_commit = get_tag_commit(cwd, head_tag)
        previous_tag = next(
            (
                tag
                for tag in merged_tags
                if tag != head_tag and get_tag_commit(cwd, tag) != head_commit
            ),
            None,
        )
        return previous_tag, head_tag

    latest_tag = merged_tags[0] if merged_tags else None
    return latest_tag, "HEAD"


class VersionManager:
    """版本管理器"""

    VERSION_TYPES = {"major", "minor", "patch"}
    INITIAL_RELEASE_VERSION = "0.1.0"

    def __init__(self, config: ReleaseConfig):
        self.config = config

    def get_current_version(self) -> str:
        """获取当前版本"""
        source = self.config.version_source

        if source == "file":
            return self._get_from_file()
        elif source == "git-tag":
            return self._get_from_git_tag()
        elif source == "script":
            raise ValueError(
                "检测到旧配置 source=script。请改成 source=file 或 source=git-tag，并保留 hook: scripts/release-version-hook.py。"
            )
        else:
            raise ValueError(f"不支持的版本来源: {source}，仅支持 file 或 git-tag")

    def resolve_version(self, value: str) -> str:
        """将版本类型或明确版本号解析为标准版本号"""
        normalized = value.strip()
        if normalized in self.VERSION_TYPES:
            return self.calculate_next(normalized)

        return self._normalize_version(normalized)

    def _normalize_version(self, version: str) -> str:
        """标准化版本号格式"""
        normalized = re.sub(r"^v", "", version.strip())
        if not re.match(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$", normalized):
            raise ValueError(f"无效的版本号: {version}")

        return normalized

    def _get_from_file(self) -> str:
        """从 VERSION 文件读取"""
        version_file = self.config.version_file
        if not version_file.exists():
            return "0.0.0"

        content = version_file.read_text(encoding="utf-8").strip()
        if not content:
            return "0.0.0"

        return self._normalize_version(content)

    def _get_from_git_tag(self) -> str:
        """从 Git tag 获取"""
        tag = get_current_release_tag(self.config.packager_root_dir, self.config.version_tag_prefix)
        if not tag:
            return "0.0.0"

        return self._normalize_version(tag.removeprefix(self.config.version_tag_prefix))

    def calculate_next(self, version_type: str = "patch") -> str:
        """计算下一个版本"""
        if version_type == "patch" and self.config.version_source == "git-tag" and not self._has_visible_release_tags():
            return self._get_initial_release_version()

        current = self.get_current_version()

        # 处理预发布版本
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", current)
        if not match:
            # 无法解析，默认 +1 patch
            return "0.0.1"

        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        prerelease = match.group(4)

        if version_type == "major":
            return f"{major + 1}.0.0{prerelease}"
        elif version_type == "minor":
            return f"{major}.{minor + 1}.0{prerelease}"
        else:
            return f"{major}.{minor}.{patch + 1}{prerelease}"

    def _has_visible_release_tags(self) -> bool:
        """当前发布线上是否已有可见的发布 tag"""
        return bool(list_release_tags(self.config.packager_root_dir, ["--merged", "HEAD"], self.config.version_tag_prefix))

    def _get_initial_release_version(self) -> str:
        """获取首发版本号"""
        version_file = self.config.version_file
        if version_file.exists():
            content = version_file.read_text(encoding="utf-8").strip()
            if content:
                return self._normalize_version(content)

        return self.INITIAL_RELEASE_VERSION

    def write_version(self, version: str) -> None:
        """写入版本文件并运行 Hook"""
        version = self._normalize_version(version)
        previous_version = self.get_current_version()
        source = self.config.version_source
        rollback = self._write_to_file(version)

        try:
            if source == "script":
                raise ValueError(
                    "检测到旧配置 source=script。请改成 source=file 或 source=git-tag，并保留 hook: scripts/release-version-hook.py。"
                )
            if source not in {"file", "git-tag"}:
                raise ValueError(f"不支持的版本来源: {source}，仅支持 file 或 git-tag")

            self._run_hook(version, previous_version, source)
        except Exception:
            rollback()
            raise

    def _write_to_file(self, version: str):
        """写入 VERSION 文件"""
        version_file = self.config.version_file
        existed = version_file.exists()
        previous_content = version_file.read_text(encoding="utf-8") if existed else None
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(f"v{version}\n", encoding="utf-8")

        def rollback() -> None:
            if existed and previous_content is not None:
                version_file.write_text(previous_content, encoding="utf-8")
            elif version_file.exists():
                version_file.unlink()

        return rollback

    def _run_hook(self, version: str, previous_version: str, source: str) -> None:
        """在写入版本后运行 Hook 脚本"""
        hook = self.config.version_hook
        if not hook:
            return

        payload = {
            "version": version,
            "previous_version": previous_version,
            "version_source": source,
            "project_root": str(self.config.packager_root_dir),
            "config_file": str(self.config.config_path.resolve()),
            "version_file": str(self.config.version_file),
            "git_tag": f"{self.config.version_tag_prefix}{version}",
        }

        payload_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                delete=False,
                dir=self.config.base_dir,
            ) as temp_file:
                json.dump(payload, temp_file, ensure_ascii=False, indent=2)
                payload_path = Path(temp_file.name)

            subprocess.run(
                [sys.executable, hook, str(payload_path)],
                check=True,
                cwd=self.config.base_dir,
            )
        finally:
            if payload_path and payload_path.exists():
                payload_path.unlink()


def get_version(config_path: str | None = None) -> str:
    """获取当前版本（便捷函数）"""
    config = ReleaseConfig(config_path)
    vm = VersionManager(config)
    return vm.get_current_version()


def calculate_next_version(version_type: str = "patch", config_path: str | None = None) -> str:
    """计算下一个版本（便捷函数）"""
    config = ReleaseConfig(config_path)
    vm = VersionManager(config)
    return vm.calculate_next(version_type)
