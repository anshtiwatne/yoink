import abc
import pathlib
import shutil
import subprocess
from typing import List, Optional, Tuple, Type, Union

class PackageManager(abc.ABC):
    """Abstract base class for package manager integrations."""
    _registered_pms: List[Type["PackageManager"]] = []

    @classmethod
    def register(cls, pm_class: Type["PackageManager"]):
        """Registers a package manager implementation."""
        if pm_class not in cls._registered_pms:
            cls._registered_pms.append(pm_class)

    @staticmethod
    def get_active() -> Optional["PackageManager"]:
        """
        Checks available package managers and returns an instance of the first
        active one found.
        """
        for pm_class in PackageManager._registered_pms:
            pm_instance = pm_class()
            if pm_instance.check_available():
                return pm_instance
        return None

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The short name of the package manager (e.g., 'apt', 'dnf')."""
        pass

    @property
    @abc.abstractmethod
    def version_separator(self) -> str:
        """The character used to separate package name and version (e.g., '=', '-')."""
        pass

    @property
    def pm_options(self) -> List[str]:
        """Default command-line options for the package manager."""
        return []

    @abc.abstractmethod
    def _check_command_path(self) -> str:
        """The command to check for availability (e.g., 'apt-get')."""
        pass

    @abc.abstractmethod
    def _check_command_args(self) -> List[str]:
        """Arguments for the availability check command (e.g., ['--version'])."""
        pass

    def check_available(self) -> bool:
        """Checks if the package manager command is available and functional."""
        cmd_path = shutil.which(self._check_command_path())
        if not cmd_path:
            return False
        try:
            subprocess.run(
                [cmd_path] + self._check_command_args(),
                capture_output=True,
                check=True,
                text=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @abc.abstractmethod
    def get_download_command(
        self, pkg_name_versioned: str, pkg_name_base: str, download_dir: pathlib.Path
    ) -> List[str]:
        """Returns the command list to download a package."""
        pass

    @abc.abstractmethod
    def find_downloaded_archive(
        self, download_dir: pathlib.Path, pkg_name_base: str
    ) -> Optional[pathlib.Path]:
        """Finds the downloaded package archive file in the download directory."""
        pass

    @abc.abstractmethod
    def get_extract_command(
        self, archive_path: pathlib.Path, install_prefix: pathlib.Path
    ) -> Tuple[Union[List[str], str], bool]:
        """
        Returns the command (list or string) to extract the archive
        and a boolean indicating if it's a shell command.
        """
        pass


def register_pm(cls: Type[PackageManager]) -> Type[PackageManager]:
    """Decorator to register a PackageManager implementation."""
    PackageManager.register(cls)
    return cls