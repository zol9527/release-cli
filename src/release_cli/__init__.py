"""Release Pilot - 自动化发布工具"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

try:
	__version__ = package_version("release-cli")
except PackageNotFoundError:
	__version__ = "0.1.0"

__author__ = "loyd"

__all__ = ["__version__", "__author__"]
