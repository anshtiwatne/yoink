import pathlib
from typing import List, Optional, Tuple

from .base import PackageManager, register_pm


@register_pm
class APT(PackageManager):
    @property
    def name(self) -> str:
        return "apt"

    @property
    def version_separator(self) -> str:
        return "="

    def _check_command_path(self) -> str:
        return "apt-get"

    def _check_command_args(self) -> List[str]:
        return ["--version"]

    def get_download_command(
        self, pkg_name_versioned: str, pkg_name_base: str, download_dir: pathlib.Path
    ) -> List[str]:
        return [
            "apt-get",
            *self.pm_options,
            "download",
            "-o",
            f"Dir::Cache::archives={download_dir.resolve()}",
            pkg_name_versioned,
        ]

    def find_downloaded_archive(
        self, download_dir: pathlib.Path, pkg_name_base: str
    ) -> Optional[pathlib.Path]:
        files = list(download_dir.glob(f"{pkg_name_base}_*.deb"))
        if not files:
            files = list(download_dir.glob(f"{pkg_name_base}*.deb"))
        return files[0] if files else None

    def get_extract_command(
        self, archive_path: pathlib.Path, install_prefix: pathlib.Path
    ) -> Tuple[List[str], bool]:
        return (
            ["dpkg", "-x", str(archive_path.resolve()), str(install_prefix.resolve())],
            False,
        )
