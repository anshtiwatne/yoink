import os
import pathlib
import shutil
import subprocess
import sys
import traceback
from typing import (
    List,
    Optional,
    Tuple,
    Union,
)

from .config import PACKAGE_CACHE_BASE
from .ui import Spinner
from .pms.base import PackageManager


def parse_package_spec(spec: str) -> Tuple[str, Optional[str]]:
    """Parses a package_spec string 'name[@version]' into (name, version)."""
    if "@" in spec:
        name, version = spec.rsplit("@", 1)
        return name, version
    return spec, None


def _run_cmd(
    cmd: Union[List[str], str],
    verbose: bool,
    check: bool = True,
    is_shell_cmd: bool = False,
) -> subprocess.CompletedProcess:
    """Helper to run a command with optional verbosity and error checking."""
    if verbose:
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        print(f"🔧 Running: {cmd_str}", file=sys.stderr)

    return subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True,
        check=check,
        shell=is_shell_cmd,
    )


def find_executable_in_prefix(
    prefix_path: pathlib.Path, command_name: str
) -> Optional[pathlib.Path]:
    """
    Searches for an executable in common bin directories within a given prefix.
    """

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
    """
    Downloads and extracts a package using the given package manager.
    Returns True on success, False on failure.
    """
    version_str = f"@{pkg_version_requested}" if pkg_version_requested else "(latest)"
    base_yoink_message = f"Casting for {pkg_name_base}{version_str}"

    spinner_instance: Optional[Spinner] = None
    if not verbose and sys.stdout.isatty():
        spinner_instance = Spinner(message=f"🎣 {base_yoink_message}")
        spinner_instance.start()
    elif verbose:
        print(f"🎣 {base_yoink_message} to {install_prefix.resolve()}")
    else:
        print(f"🎣 {base_yoink_message} ...", end="", flush=True)

    pkg_name_versioned = (
        f"{pkg_name_base}{pm.version_separator}{pkg_version_requested}"
        if pkg_version_requested
        else pkg_name_base
    )

    temp_download_dir_name = f"yoink_dl_{pm.name}_{pkg_name_base.replace('/', '_')}_{pkg_version_requested or 'latest'}_{os.getpid()}_{pathlib.Path(install_prefix).name}"
    temp_download_dir = (
        PACKAGE_CACHE_BASE / "downloads" / temp_download_dir_name
    ).resolve()

    is_successful_yoink = False
    final_user_message = ""

    try:
        temp_download_dir.mkdir(parents=True, exist_ok=True)

        if verbose:
            print(f" reeling in the line (downloading {pkg_name_versioned})...")
        download_cmd = pm.get_download_command(
            pkg_name_versioned, pkg_name_base, temp_download_dir
        )
        _run_cmd(download_cmd, verbose)

        archive_file = pm.find_downloaded_archive(temp_download_dir, pkg_name_base)
        if not archive_file or not archive_file.exists():
            is_successful_yoink = False
            final_user_message = f"The line came back empty! (No archive for {pkg_name_base} in {temp_download_dir})"
            if verbose:
                print(
                    f"🔎 Checked in: {temp_download_dir}, found: {[item.name for item in temp_download_dir.iterdir() if item.is_file()]}",
                    file=sys.stderr,
                )
        else:
            if verbose:
                print(f"📄 Got it! Archive: {archive_file.name}")
                print(" unhooking the catch (extracting)...")

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
            print(f"😫 {final_user_message}", file=sys.stderr)
            cmd_str = " ".join(e.cmd) if isinstance(e.cmd, list) else e.cmd
            print(f"Failed command: {cmd_str}", file=sys.stderr)
            if e.stdout:
                print(f"Stdout:\n{e.stdout}", file=sys.stderr)
            if e.stderr:
                print(f"Stderr:\n{e.stderr}", file=sys.stderr)
        else:
            print(f"\n😫 {final_user_message}", file=sys.stderr)
            error_summary = (e.stderr or e.stdout or str(e)).strip()
            if error_summary:
                print(
                    f"PM Error: {error_summary[:200]}{'...' if len(error_summary) > 200 else ''}",
                    file=sys.stderr,
                )
            else:
                print("No detailed error output from command.", file=sys.stderr)
            print("(Run with --verbose for full command output)", file=sys.stderr)

    except Exception as e:
        is_successful_yoink = False
        final_user_message = (
            f"A rogue wave hit! (Unexpected error yoinking {pkg_name_base})"
        )
        if verbose:
            print(f"😫 {final_user_message}", file=sys.stderr)
            print(f"Error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        else:
            print(f"\n😫 {final_user_message}", file=sys.stderr)
            print(
                f"Error detail: {str(e)[:200]}{'...' if len(str(e)) > 200 else ''}",
                file=sys.stderr,
            )
            print("(Run with --verbose for full traceback)", file=sys.stderr)
    finally:
        if spinner_instance:
            spinner_instance.stop(
                success=is_successful_yoink, result_message=final_user_message
            )
        elif not verbose and not sys.stdout.isatty():
            if final_user_message:
                print(
                    f" {final_user_message if is_successful_yoink else final_user_message.replace('Oops! The line snapped!', 'Failed').replace('A rogue wave hit!', 'Failed')}"
                )
            else:
                print(" Done." if is_successful_yoink else " Failed.")

        if not is_successful_yoink and install_prefix.exists():
            if verbose:
                print(
                    f"🗑️ Cleaning up failed installation attempt at {install_prefix}",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix, ignore_errors=True)

        if temp_download_dir.exists():
            shutil.rmtree(temp_download_dir, ignore_errors=True)

    return is_successful_yoink


def purge_cache():
    """Removes the entire Yoink package cache."""
    spinner = Spinner(
        message="🎣 Sweeping the deck (purging cache)", active_on_tty_only=True
    )
    success = False
    message = ""
    spinner.start()
    if PACKAGE_CACHE_BASE.exists():
        try:
            shutil.rmtree(PACKAGE_CACHE_BASE)

            PACKAGE_CACHE_BASE.mkdir(parents=True, exist_ok=True)
            message = (
                f"Yoink cache at {PACKAGE_CACHE_BASE.resolve()} is now squeaky clean!"
            )
            success = True
        except OSError as e:
            message = f"Error purging cache {PACKAGE_CACHE_BASE.resolve()}: {e}"
            success = False
            print(f"\nError: {message}", file=sys.stderr)
    else:
        message = (
            f"Tackle box empty! (Cache {PACKAGE_CACHE_BASE.resolve()} does not exist)"
        )
        success = True
    spinner.stop(success=success, result_message=message)
