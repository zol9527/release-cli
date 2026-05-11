"""打包器模块"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tomllib
import zipfile
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING

from .config import ReleaseConfig

if TYPE_CHECKING:
    from pathlib import Path


class Packager:
    """打包器"""

    def __init__(self, config: ReleaseConfig):
        self.config = config

    def get_package_name(self, version: str) -> str:
        """获取包名"""
        name_template = self.config.packager_name

        # 获取项目名
        project_name = self._get_project_name()

        # 替换变量
        now = datetime.now()
        replacements = {
            "{name}": project_name,
            "{version}": version,
            "{date}": now.strftime("%Y-%m-%d"),
            "{datetime}": now.strftime("%Y-%m-%d-%H%M%S"),
        }

        result = name_template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)

        return result

    def _get_project_name(self) -> str:
        """获取项目名"""
        root = self.config.packager_root_dir

        pkg_file = root / "package.json"
        if pkg_file.exists():
            pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
            return pkg.get("name", "app")

        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                pyproject_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                return pyproject_data.get("project", {}).get("name", "app")
            except Exception:
                pass

        go_mod = root / "go.mod"
        if go_mod.exists():
            content = go_mod.read_text(encoding="utf-8")
            match = re.search(r"module\s+([^\s]+)", content)
            if match:
                return match.group(1).split("/")[-1]

        return root.name or "app"

    def create_package(self, version: str, output_dir: Path | None = None) -> Path:
        """创建安装包"""
        output_dir = output_dir or self.config.packager_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        package_name = self.get_package_name(version)
        output_path = output_dir / f"{package_name}.zip"
        archive_root = self.config.packager_root_dir
        files = self._collect_files(output_dir)
        if not files:
            raise ValueError("未匹配到任何需要打包的文件")

        self._create_zip(files, output_path, archive_root)
        return output_path

    def _collect_files(self, output_dir: Path) -> list[Path]:
        """根据配置收集需要打包的文件列表"""
        root = self.config.packager_root_dir
        exclude_patterns = self._exclude_patterns()
        output_exclude_patterns: list[str] = []
        with suppress(ValueError):
            output_exclude_patterns.append(output_dir.resolve().relative_to(root).as_posix())

        files = self._collect_pattern_files(self.config.packager_include, root)
        files = self._filter_gitignored(files, root)
        files = self._filter_excluded(files, root, exclude_patterns + output_exclude_patterns)

        force_files = self._collect_pattern_files(self.config.packager_force_include, root)
        collected = dict.fromkeys(files)
        collected.update(dict.fromkeys(force_files))
        files = list(collected)
        files = self._filter_excluded(files, root, output_exclude_patterns)

        return sorted(files, key=lambda item: item.relative_to(root).as_posix())

    def _collect_pattern_files(self, patterns: list[str], root: Path) -> list[Path]:
        """按配置模式收集候选文件"""
        collected: dict[Path, None] = {}

        for pattern in patterns:
            if pattern.startswith("!"):
                continue

            for path in root.glob(pattern):
                if path.is_file():
                    collected[path] = None
                    continue

                if path.is_dir():
                    for file_path in path.rglob("*"):
                        if not file_path.is_file():
                            continue
                        collected[file_path] = None

        return list(collected)

    def _exclude_patterns(self) -> list[str]:
        """合并新旧配置格式的排除模式"""
        patterns = list(self.config.packager_exclude)
        patterns.extend(
            pattern[1:] for pattern in self.config.packager_include if pattern.startswith("!")
        )
        return patterns

    def _is_excluded(self, path: Path, patterns: list[str]) -> bool:
        """检查文件是否命中排除规则"""
        path_str = path.as_posix()
        return any(self._match_pattern(path_str, pattern) for pattern in patterns)

    def _filter_excluded(self, files: list[Path], root: Path, patterns: list[str]) -> list[Path]:
        """按 exclude 规则过滤文件列表"""
        if not patterns:
            return files

        return [file for file in files if not self._is_excluded(file.relative_to(root), patterns)]

    def _filter_gitignored(self, files: list[Path], root: Path) -> list[Path]:
        """根据 Git ignore 规则过滤候选文件

        这里直接复用 `git check-ignore --no-index`, 避免在 Python 里重新实现
        `.gitignore` 的目录匹配、通配符、取反规则和多层 ignore 文件语义。
        如果当前目录不是 Git 工作区, 或运行环境没有 git, 则保持原候选列表不变。
        """
        if not self.config.packager_respect_gitignore or not files:
            return files

        relative_paths = [file.relative_to(root).as_posix() for file in files]
        check_input = "\n".join(relative_paths) + "\n"

        try:
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", "--stdin"],
                cwd=root,
                input=check_input,
                text=True,
                capture_output=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return files

        # 0 表示存在命中项, 1 表示没有任何命中项; 其他状态通常是非 Git 工作区等环境问题。
        if result.returncode == 1:
            return files
        if result.returncode != 0:
            return files

        ignored_paths = {line for line in result.stdout.splitlines() if line}
        return [
            file
            for file, relative_path in zip(files, relative_paths, strict=True)
            if relative_path not in ignored_paths
        ]

    def _match_pattern(self, path: str, pattern: str) -> bool:
        """检查路径是否匹配模式"""
        normalized = pattern.strip().rstrip("/")
        if not normalized:
            return False

        return (
            fnmatch.fnmatch(path, normalized)
            or fnmatch.fnmatch(path, f"*/{normalized}")
            or path == normalized
            or path.startswith(f"{normalized}/")
        )

    def _create_zip(self, files: list[Path], dest: Path, archive_root: Path) -> None:
        """创建 ZIP 包"""
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in files:
                zf.write(file, file.resolve().relative_to(archive_root))


def create_package(version: str, config_path: str | None = None) -> Path:
    """创建安装包(便捷函数)"""
    config = ReleaseConfig(config_path)
    packager = Packager(config)
    return packager.create_package(version)
