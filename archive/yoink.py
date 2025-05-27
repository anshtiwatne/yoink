#!/usr/bin/env python3

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import abc
import time
import threading
from typing import (
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

PACKAGE_CACHE_BASE = pathlib.Path("/tmp/yoink")


class Spinner:
    """A simple CLI spinner with a yoinking theme that completes its cycle."""

    def __init__(self, message="Yoinking...", delay=0.15, active_on_tty_only=True):
        self.spinner_frames = [
            "🎣--~       ",
            "🎣---~      ",
            "🎣----~     ",
            "🎣-----~    ",
            "🎣------~   ",
            "🎣-------~  ",
            "🎣--------~ ",
            "🎣--------~🐟",
            "🎣-------🐟 ",
            "🎣------🐟  ",
            "🎣-----🐟   ",
            "🎣----🐟    ",
            "🎣---🐟     ",
            "🎣--🐟      ",
            "🎣-🐟       ",
            "🎣🐟        ",
        ]
        self.delay = delay
        self.base_message = message
        self._running = False
        self._stop_requested = False
        self._cycle_complete_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.active_on_tty_only = active_on_tty_only
        self.is_tty = sys.stdout.isatty()
        self.current_frame_idx = 0
        self._max_spinner_frame_len = max(len(s) for s in self.spinner_frames)

    def _spin(self):
        self.current_frame_idx = 0
        while self._running:
            if self._stop_requested and self.current_frame_idx == 0:
                self._running = False
                self._cycle_complete_event.set()
                break

            spinner_frame = self.spinner_frames[self.current_frame_idx]
            output_line = f"\r{self.base_message} {spinner_frame}"

            padding_len = self._max_spinner_frame_len - len(spinner_frame) + 2
            padding = " " * padding_len
            print(output_line + padding, end="")
            sys.stdout.flush()

            time.sleep(self.delay)
            self.current_frame_idx = (self.current_frame_idx + 1) % len(
                self.spinner_frames
            )

            if self.current_frame_idx == 0 and self._stop_requested:
                self._running = False
                self._cycle_complete_event.set()

    def start(self):
        if self.active_on_tty_only and not self.is_tty:
            print(f"{self.base_message} ...", end="")
            sys.stdout.flush()
            return

        if not self._running:
            self._stop_requested = False
            self._cycle_complete_event.clear()
            self._running = True
            self.current_frame_idx = 0
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()

    def stop(
        self,
        success: bool,
        result_message: Optional[str] = None,
        success_char: str = "🐟",
        failure_char: str = "😫",
    ):
        if self.active_on_tty_only and not self.is_tty:
            if result_message:
                print(f" {result_message}")
            else:
                print(" Done." if success else " Failed.")
            sys.stdout.flush()
            return

        if self._running:
            if not self._stop_requested:
                self._stop_requested = True

            if self._thread and self._thread.is_alive():
                timeout_duration = len(self.spinner_frames) * self.delay + 1.5
                completed_gracefully = self._cycle_complete_event.wait(
                    timeout=timeout_duration
                )
                if not completed_gracefully:
                    self._running = False

                    self._thread.join(timeout=0.2)

            clear_line_len = (
                len(self.base_message) + 1 + self._max_spinner_frame_len + 2
            )
            clear_line_str = "\r" + " " * clear_line_len + "\r"
            print(clear_line_str, end="")
            sys.stdout.flush()

        final_char = success_char if success else failure_char
        if result_message:
            print(f"{final_char} {result_message}")
        else:
            default_msg = "Operation complete." if success else "Operation failed."
            print(f"{final_char} {default_msg}")
        sys.stdout.flush()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        is_success = exc_type is None
        exit_message = None
        if not is_success:
            exit_message = "An unexpected error occurred."

        self.stop(
            success=is_success,
            result_message=exit_message,
            success_char="🎉",
            failure_char="🌊",
        )
        return False


class PackageManager(abc.ABC):
    _registered_pms: List[Type["PackageManager"]] = []

    @classmethod
    def register(cls, pm_class: Type["PackageManager"]):
        if pm_class not in cls._registered_pms:
            cls._registered_pms.append(pm_class)

    @staticmethod
    def get_active() -> Optional["PackageManager"]:
        for pm_class in PackageManager._registered_pms:
            pm_instance = pm_class()
            if pm_instance.check_available():
                return pm_instance
        return None

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def version_separator(self) -> str:
        pass

    @property
    def pm_options(self) -> List[str]:
        return []

    @abc.abstractmethod
    def _check_command_path(self) -> str:
        pass

    @abc.abstractmethod
    def _check_command_args(self) -> List[str]:
        pass

    def check_available(self) -> bool:
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
        pass

    @abc.abstractmethod
    def find_downloaded_archive(
        self, download_dir: pathlib.Path, pkg_name_base: str
    ) -> Optional[pathlib.Path]:
        pass

    @abc.abstractmethod
    def get_extract_command(
        self, archive_path: pathlib.Path, install_prefix: pathlib.Path
    ) -> Tuple[Union[List[str], str], bool]:
        pass


def register_pm(cls: Type[PackageManager]) -> Type[PackageManager]:
    PackageManager.register(cls)
    return cls


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
        return files[0] if files else None

    def get_extract_command(
        self, archive_path: pathlib.Path, install_prefix: pathlib.Path
    ) -> Tuple[List[str], bool]:
        return (
            ["dpkg", "-x", str(archive_path.resolve()), str(install_prefix.resolve())],
            False,
        )


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
            f'rpm2cpio "{archive_path.resolve()}" | (cd "{install_prefix.resolve()}" && cpio -idum)',
            True,
        )


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
        extensions = [".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar.gz", ".pkg.tar.bz2"]
        for ext_suffix in extensions:
            files = list(download_dir.glob(f"{pkg_name_base}-*{ext_suffix}"))
            if files:
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


def parse_package_spec(spec: str) -> Tuple[str, Optional[str]]:
    if "@" in spec:
        name, version = spec.rsplit("@", 1)
        return name, version
    return spec, None


def _run_cmd(
    cmd: Union[List[str], str],
    verbose: bool,
    check: bool = True,
    is_shell_cmd: bool = False,
):
    if verbose:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        print(f"🔧 Running: {cmd_str}", file=sys.stderr)

    return subprocess.run(
        cmd, capture_output=not verbose, text=True, check=check, shell=is_shell_cmd
    )


def find_executable_in_prefix(
    prefix_path: pathlib.Path, command_name: str
) -> Optional[pathlib.Path]:
    search_dirs = [
        prefix_path / "bin",
        prefix_path / "usr" / "bin",
        prefix_path / "sbin",
        prefix_path / "usr" / "sbin",
        prefix_path / "usr" / "local" / "bin",
        prefix_path,
    ]
    for directory in search_dirs:
        if directory.is_dir():
            executable_path = directory / command_name
            if executable_path.is_file() and os.access(executable_path, os.X_OK):
                return executable_path.resolve()
    return None


def yoink_package(
    pm: PackageManager,
    pkg_name_base: str,
    pkg_version_requested: Optional[str],
    install_prefix: pathlib.Path,
    verbose: bool,
) -> bool:
    version_str = f"@{pkg_version_requested}" if pkg_version_requested else "(latest)"
    base_yoink_message = f"Casting for {pkg_name_base}{version_str}"

    spinner: Optional[Spinner] = None
    if not verbose and sys.stdout.isatty():
        spinner = Spinner(message=f"🎣 {base_yoink_message}")
        spinner.start()
    elif verbose:
        print(f"🎣 {base_yoink_message} to {install_prefix.resolve()}")
    else:
        print(f"🎣 {base_yoink_message} ...", end="", flush=True)

    pkg_name_versioned = (
        f"{pkg_name_base}{pm.version_separator}{pkg_version_requested}"
        if pkg_version_requested
        else pkg_name_base
    )

    temp_download_dir_name = f"yoink_dl_{pm.name}_{pkg_name_base.replace('/', '_')}_{pkg_version_requested or 'latest'}_{os.getpid()}"
    temp_download_dir = (
        PACKAGE_CACHE_BASE / "downloads" / temp_download_dir_name
    ).resolve()

    is_successful_yoink = False
    final_user_message = ""

    try:
        temp_download_dir.mkdir(parents=True, exist_ok=True)

        if verbose:
            print("Reeling in the line (downloading)...")
        download_cmd = pm.get_download_command(
            pkg_name_versioned, pkg_name_base, temp_download_dir
        )
        _run_cmd(download_cmd, verbose)

        archive_file = pm.find_downloaded_archive(temp_download_dir, pkg_name_base)
        if not archive_file or not archive_file.exists():
            is_successful_yoink = False
            final_user_message = (
                f"The line came back empty! (No archive for {pkg_name_base})"
            )
            if verbose:
                print(
                    f"🔎 Checked in: {temp_download_dir}, found: {[item.name for item in temp_download_dir.iterdir()]}",
                    file=sys.stderr,
                )
        else:
            if verbose:
                print(f"📄 Got it! Archive: {archive_file.name}")
                print("Unhooking the catch (extracting)...")

            install_prefix.mkdir(parents=True, exist_ok=True)
            extract_cmd, is_shell_cmd = pm.get_extract_command(
                archive_file, install_prefix
            )
            _run_cmd(extract_cmd, verbose, is_shell_cmd=is_shell_cmd)

            (install_prefix / ".yoinked").touch()
            is_successful_yoink = True
            final_user_message = f"Caught {pkg_name_base} from {pm.name}!"
            if verbose:
                print(f"🎉 {final_user_message}")

    except subprocess.CalledProcessError as e:
        is_successful_yoink = False
        final_user_message = f"Oops! The line snapped! (Error yoinking {pkg_name_base})"
        if verbose:
            print(f"😫 {final_user_message}")
        print("More details on the snag:", file=sys.stderr)
        if verbose:
            cmd_str = " ".join(e.cmd) if isinstance(e.cmd, list) else e.cmd
            print(f"Failed command: {cmd_str}", file=sys.stderr)
            if e.stdout:
                print(f"Stdout:\n{e.stdout}", file=sys.stderr)
            if e.stderr:
                print(f"Stderr:\n{e.stderr}", file=sys.stderr)
        elif e.stderr and len(e.stderr.strip()) > 0:
            print(f"PM Error: {e.stderr.strip()[:200]}", file=sys.stderr)
        else:
            print("(Run with --verbose for full command output)", file=sys.stderr)

    except Exception as e:
        is_successful_yoink = False
        final_user_message = (
            f"A rogue wave hit! (Unexpected error yoinking {pkg_name_base})"
        )
        if verbose:
            print(f"😫 {final_user_message}")
        print("More details on the snag:", file=sys.stderr)
        if verbose:
            import traceback

            print(f"Error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        else:
            print(f"Error detail: {str(e)[:200]}", file=sys.stderr)
            print("(Run with --verbose for full traceback)", file=sys.stderr)
    finally:
        if spinner:
            spinner.stop(success=is_successful_yoink, result_message=final_user_message)
        elif not verbose and not sys.stdout.isatty():
            print(
                f" {final_user_message}"
                if final_user_message
                else (" Done." if is_successful_yoink else " Failed.")
            )

        if not is_successful_yoink and install_prefix.exists():
            if verbose:
                print(
                    f"🗑️ Cleaning up failed installation at {install_prefix}",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix)

        if temp_download_dir.exists():
            shutil.rmtree(temp_download_dir)

    return is_successful_yoink


def purge_cache():
    spinner = Spinner(
        message="🎣 Sweeping the deck (purging cache)", active_on_tty_only=True
    )
    success = False
    message = ""
    spinner.start()
    if PACKAGE_CACHE_BASE.exists():
        try:
            shutil.rmtree(PACKAGE_CACHE_BASE)
            message = (
                f"Yoink cache at {PACKAGE_CACHE_BASE.resolve()} is now squeaky clean!"
            )
            success = True
        except OSError as e:
            message = f"Error purging cache {PACKAGE_CACHE_BASE.resolve()}: {e}"
            success = False
    else:
        message = (
            f"Tackle box empty! (Cache {PACKAGE_CACHE_BASE.resolve()} does not exist)"
        )
        success = True
    spinner.stop(success=success, result_message=message)


def main():
    parser = argparse.ArgumentParser(
        description="Yoink - Minimal npx-like tool for temporary system packages.",
        epilog="Examples:\n  yoink cowsay 'Moo!'\n  yoink sl\n  yoink --purge-cache\n  yoink htop@3.3.0",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--purge-cache",
        action="store_true",
        help="Remove all yoinked packages and data, then exit.",
    )
    parser.add_argument(
        "package_spec",
        nargs="?",
        help="Package to yoink, e.g., 'cowsay' or 'sl@5.02'. Version format depends on PM.",
    )
    parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the yoinked package's command.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed diagnostic output."
    )

    args = parser.parse_args()

    PACKAGE_CACHE_BASE.mkdir(parents=True, exist_ok=True)

    if args.purge_cache:
        purge_cache()
        sys.exit(0)

    if not args.package_spec:
        parser.print_help(sys.stderr)
        sys.exit(1)

    active_pm = PackageManager.get_active()
    if not active_pm:
        print(
            "❌ No supported package manager (apt, dnf, pacman) found or functional on this system.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.verbose:
        print(f"🔧 Using package manager: {active_pm.name}", file=sys.stderr)

    pkg_name_base, pkg_version_requested = parse_package_spec(args.package_spec)
    command_to_run = pkg_name_base
    command_run_args = args.command_args

    if args.verbose and args.command_args:
        print(
            f"🔧 Will run '{command_to_run}' with arguments: {command_run_args}",
            file=sys.stderr,
        )

    cache_subdir_name = pkg_name_base.replace("/", "_")
    install_prefix = (PACKAGE_CACHE_BASE / active_pm.name / cache_subdir_name).resolve()
    executable_path: Optional[pathlib.Path] = None
    yoink_is_needed = True

    if pkg_version_requested:
        if args.verbose:
            print(
                f"🔧 Version '{pkg_version_requested}' specifically requested. Will yoink to ensure correct version.",
                file=sys.stderr,
            )
        if install_prefix.exists():
            if args.verbose:
                print(
                    f"🗑️ Removing existing cache for {pkg_name_base} at {install_prefix} to fetch specific version.",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix)
    elif install_prefix.exists() and (install_prefix / ".yoinked").is_file():
        executable_path = find_executable_in_prefix(install_prefix, command_to_run)
        if executable_path:
            if not args.verbose:
                print(
                    f"🎣 Using cached {pkg_name_base} from {install_prefix.relative_to(PACKAGE_CACHE_BASE) if PACKAGE_CACHE_BASE in install_prefix.parents else install_prefix}"
                )
            else:
                print(
                    f"🎣 Using cached {pkg_name_base} (found '{command_to_run}' at {executable_path})",
                    file=sys.stderr,
                )
            yoink_is_needed = False
        else:
            if args.verbose:
                print(
                    f"🤔 Cache for {pkg_name_base} exists with .yoinked, but its command '{command_to_run}' not found. Re-yoinking.",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix)
    else:
        if install_prefix.exists():
            if args.verbose:
                print(
                    f"🤔 Cache for {pkg_name_base} at {install_prefix} exists but is incomplete or not marked .yoinked. Re-yoinking.",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix)

    if yoink_is_needed:
        if not yoink_package(
            active_pm,
            pkg_name_base,
            pkg_version_requested,
            install_prefix,
            args.verbose,
        ):
            print(
                f"❌ Failed to yoink {pkg_name_base}. See messages above.",
                file=sys.stderr,
            )
            sys.exit(1)

        executable_path = find_executable_in_prefix(install_prefix, command_to_run)
        if not executable_path:
            print(
                f"❌ Command '{command_to_run}' (from package '{pkg_name_base}') not found in {install_prefix} after yoinking.",
                file=sys.stderr,
            )
            print(
                "Searched in standard bin locations within the prefix. Check package contents or name.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.verbose:
            print(
                f"🔧 Successfully yoinked and found '{command_to_run}' at {executable_path}",
                file=sys.stderr,
            )

    current_env = os.environ.copy()
    potential_bin_dirs = ["bin", "usr/bin", "sbin", "usr/sbin", "usr/local/bin"]
    new_path_entries = [
        str(p.resolve())
        for d_name in potential_bin_dirs
        if (p := install_prefix / d_name).is_dir()
    ]

    if new_path_entries:
        current_env["PATH"] = (
            os.pathsep.join(new_path_entries) + os.pathsep + current_env.get("PATH", "")
        )
        if args.verbose:
            print(
                f"🔧 Environment PATH prepended with: {os.pathsep.join(new_path_entries)}",
                file=sys.stderr,
            )

    full_command_to_exec = [str(executable_path)] + command_run_args
    if args.verbose:
        print(
            f"🚀 Executing: {' '.join(full_command_to_exec)} (resolved from {executable_path})",
            file=sys.stderr,
        )

    try:
        os.execvpe(str(executable_path), full_command_to_exec, current_env)
    except OSError as e:
        print(
            f"❌ Failed to execute '{command_to_run}' (from {executable_path}): {e}",
            file=sys.stderr,
        )
        sys.exit(127)


if __name__ == "__main__":
    main()
