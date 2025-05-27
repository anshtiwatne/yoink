import os
import pathlib
from typing import List, Optional, Tuple

from .base import PackageManager, register_pm


@register_pm
class Pacman(PackageManager):
    @property
    def name(self) -> str:
        return "pacman"

    @property
    def version_separator(self) -> str:
        return "="

    @property
    def pm_options(self) -> List[str]:
        return ["--noconfirm", "--quiet"]

    def _check_command_path(self) -> str:
        return "pacman"

    def _check_command_args(self) -> List[str]:
        return ["--version"]

    def get_download_command(
        self, pkg_name_versioned: str, pkg_name_base: str, download_dir: pathlib.Path
    ) -> List[str]:
        cmd_prefix = []

        if os.geteuid() != 0:
            cmd_prefix.append("sudo")

        return [
            *cmd_prefix,
            "pacman",
            *self.pm_options,
            "-Sddp",
            "--cachedir",
            str(download_dir.resolve()),
            pkg_name_versioned,
        ]

    def find_downloaded_archive(
        self, download_dir: pathlib.Path, pkg_name_base: str
    ) -> Optional[pathlib.Path]:
        extensions = [
            ".pkg.tar.zst",
            ".pkg.tar.xz",
            ".pkg.tar.gz",
            ".pkg.tar.bz2",
            ".pkg.tar",
        ]
        for ext_suffix in extensions:
            files = list(download_dir.glob(f"{pkg_name_base}-*{ext_suffix}"))
            if files:
                files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                return files[0]
        return None

    def get_extract_command(
        self, archive_path: pathlib.Path, install_prefix: pathlib.Path
    ) -> Tuple[List[str], bool]:
        return (
            [
                "tar",
                "-xf",
                str(archive_path.resolve()),
                "-C",
                str(install_prefix.resolve()),
            ],
            False,
        )
