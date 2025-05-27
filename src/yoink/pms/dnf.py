import pathlib
from typing import List, Optional, Tuple

from .base import PackageManager, register_pm


@register_pm
class DNF(PackageManager):
    @property
    def name(self) -> str:
        return "dnf"

    @property
    def version_separator(self) -> str:
        return "-"

    @property
    def pm_options(self) -> List[str]:
        return ["--setopt=install_weak_deps=False", "--quiet"]

    def _check_command_path(self) -> str:
        return "dnf"

    def _check_command_args(self) -> List[str]:
        return ["--version"]

    def get_download_command(
        self, pkg_name_versioned: str, pkg_name_base: str, download_dir: pathlib.Path
    ) -> List[str]:
        return [
            "dnf",
            *self.pm_options,
            "download",
            f"--destdir={download_dir.resolve()}",
            pkg_name_versioned,
        ]

    def find_downloaded_archive(
        self, download_dir: pathlib.Path, pkg_name_base: str
    ) -> Optional[pathlib.Path]:
        files = list(download_dir.glob(f"{pkg_name_base}-*.rpm"))
        if not files:
            files = list(download_dir.glob(f"{pkg_name_base}*.rpm"))
        return files[0] if files else None

    def get_extract_command(
        self, archive_path: pathlib.Path, install_prefix: pathlib.Path
    ) -> Tuple[str, bool]:
        return (
            f'rpm2cpio "{archive_path.resolve()}" | (cd "{install_prefix.resolve()}" && cpio -idum --quiet)',
            True,
        )
