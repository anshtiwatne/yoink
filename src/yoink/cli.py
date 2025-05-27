import argparse
import os
import pathlib
import shutil
import sys
from typing import Optional

from .config import PACKAGE_CACHE_BASE
from .pms.base import PackageManager
from .yoink_engine import (
    parse_package_spec,
    find_executable_in_prefix,
    yoink_package,
    purge_cache,
)


def main():
    parser = argparse.ArgumentParser(
        description="Yoink - Minimal npx-like tool for temporary system packages.",
        epilog="Examples:\n"
        "  yoink cowsay 'Moo!'\n"
        "  yoink sl\n"
        "  yoink --purge-cache\n"
        "  yoink htop@3.3.0 (version syntax depends on your system's package manager)\n",
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
        help="Package to yoink, e.g., 'cowsay' or 'sl@version'. Version format depends on PM.",
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

    try:
        PACKAGE_CACHE_BASE.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"❌ Error creating cache directory {PACKAGE_CACHE_BASE}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

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
            f"🔧 Will attempt to run '{command_to_run}' from yoinked package '{pkg_name_base}' "
            f"with arguments: {command_run_args}",
            file=sys.stderr,
        )
    elif args.verbose:
        print(
            f"🔧 Will attempt to run '{command_to_run}' from yoinked package '{pkg_name_base}'",
            file=sys.stderr,
        )

    safe_pkg_name_for_dir = pkg_name_base.replace("/", "_").replace(":", "_")

    version_suffix = f"@{pkg_version_requested}" if pkg_version_requested else "_latest"
    cache_subdir_name = f"{safe_pkg_name_for_dir}{version_suffix}"

    install_prefix = (PACKAGE_CACHE_BASE / active_pm.name / cache_subdir_name).resolve()

    executable_path: Optional[pathlib.Path] = None
    yoink_is_needed = True

    if pkg_version_requested:
        if args.verbose:
            print(
                f"🔧 Version '{pkg_version_requested}' specifically requested for {pkg_name_base}.",
                file=sys.stderr,
            )
        if install_prefix.exists():
            if args.verbose:
                print(
                    f"🗑️ Removing existing versioned cache for {pkg_name_base}@{pkg_version_requested} at {install_prefix} to ensure fresh fetch.",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix)

        yoink_is_needed = True
    elif install_prefix.exists() and (install_prefix / ".yoinked").is_file():
        executable_path = find_executable_in_prefix(install_prefix, command_to_run)
        if executable_path:
            relative_cache_path = (
                install_prefix.relative_to(PACKAGE_CACHE_BASE)
                if PACKAGE_CACHE_BASE in install_prefix.parents
                else install_prefix
            )
            if not args.verbose and sys.stdout.isatty():
                print(f"🎣 Using cached {pkg_name_base} from {relative_cache_path}")
            elif args.verbose:
                print(
                    f"🎣 Using cached {pkg_name_base} (found '{command_to_run}' at {executable_path}) from {relative_cache_path}",
                    file=sys.stderr,
                )
            yoink_is_needed = False
        else:
            if args.verbose:
                print(
                    f"🤔 Cache for {pkg_name_base} (latest) at {install_prefix} exists with .yoinked, "
                    f"but its command '{command_to_run}' not found. Re-yoinking.",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix)
            yoink_is_needed = True
    else:
        if install_prefix.exists():
            if args.verbose:
                print(
                    f"🤔 Cache for {pkg_name_base} (latest) at {install_prefix} exists but is incomplete "
                    f"(no .yoinked marker). Re-yoinking.",
                    file=sys.stderr,
                )
            shutil.rmtree(install_prefix)
        yoink_is_needed = True

    if yoink_is_needed:
        if not yoink_package(
            active_pm,
            pkg_name_base,
            pkg_version_requested,
            install_prefix,
            args.verbose,
        ):
            print(
                f"❌ Failed to yoink {pkg_name_base}{'@' + pkg_version_requested if pkg_version_requested else ''}. See messages above.",
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
                "   Searched in standard bin locations within the prefix. Check package contents or ensure the command name matches an executable in the package.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.verbose:
            print(
                f"🔧 Successfully yoinked and found '{command_to_run}' at {executable_path}",
                file=sys.stderr,
            )

    if not executable_path:
        print(
            f"❌ Internal error: Executable path for '{command_to_run}' not determined.",
            file=sys.stderr,
        )
        sys.exit(1)

    current_env = os.environ.copy()

    potential_bin_dirs_relative = [
        "bin",
        "usr/bin",
        "sbin",
        "usr/sbin",
        "usr/local/bin",
    ]
    new_path_entries = []
    for d_name in potential_bin_dirs_relative:
        abs_dir_path = install_prefix / d_name
        if abs_dir_path.is_dir():
            new_path_entries.append(str(abs_dir_path.resolve()))

    if (
        install_prefix.is_dir()
        and str(install_prefix.resolve()) not in new_path_entries
    ):
        if any(
            os.access(item, os.X_OK)
            for item in install_prefix.iterdir()
            if item.is_file()
        ):
            new_path_entries.append(str(install_prefix.resolve()))

    if new_path_entries:
        current_env["PATH"] = (
            os.pathsep.join(new_path_entries) + os.pathsep + current_env.get("PATH", "")
        )
        if args.verbose:
            print(
                f"🔧 Environment PATH prepended with: {os.pathsep.join(new_path_entries)}",
                file=sys.stderr,
            )
    elif args.verbose:
        print(
            f"🔧 No additional bin directories found in {install_prefix} to add to PATH.",
            file=sys.stderr,
        )

    full_command_to_exec = [str(executable_path)] + command_run_args
    if args.verbose:
        print(
            f"🚀 Executing: {' '.join(full_command_to_exec)} (resolved from {executable_path})",
            file=sys.stderr,
        )
        if "PATH" in current_env:
            print(f"   with PATH: {current_env['PATH']}", file=sys.stderr)

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
