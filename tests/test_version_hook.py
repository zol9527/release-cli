from __future__ import annotations

from pathlib import Path

from release_cli.config import ReleaseConfig
from release_cli.version import VersionManager


def test_version_hook_payload_temp_file_is_removed(tmp_path: Path) -> None:
    """确认 release-cli 在 hook 执行完成后清理临时 payload 文件。"""
    hook_file = tmp_path / "hook-version.py"
    hook_file.write_text(
        "from pathlib import Path\n"
        "import json\n"
        "import sys\n\n"
        "payload_path = Path(sys.argv[1])\n"
        "payload = json.loads(payload_path.read_text(encoding='utf-8'))\n"
        "assert payload_path.exists()\n"
        "(payload_path.parent / 'payload-name.txt').write_text(payload_path.name, encoding='utf-8')\n"
        "(payload_path.parent / 'hook-version.txt').write_text(payload['version'], encoding='utf-8')\n",
        encoding="utf-8",
    )
    config_file = tmp_path / ".release.yml"
    config_file.write_text(
        "version:\n"
        "  source: file\n"
        "  file: VERSION\n"
        "  hook: hook-version.py\n"
        "packager:\n"
        "  root_dir: .\n",
        encoding="utf-8",
    )

    VersionManager(ReleaseConfig(config_file)).write_version("1.2.3")

    payload_name = (tmp_path / "payload-name.txt").read_text(encoding="utf-8")
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == "v1.2.3\n"
    assert (tmp_path / "hook-version.txt").read_text(encoding="utf-8") == "1.2.3"
    assert not (tmp_path / payload_name).exists()
