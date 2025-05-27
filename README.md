# Yoink

Yoink is a minimal, npx-like tool for temporarily downloading, caching, and running linux packages using your distro's package manager

## Features

- Automatically detects and uses `apt`, `dnf`, or `pacman`
- Downloads packages to a temporary cache (`/tmp/yoink` by default)
- Executes commands from the yoinked package in an isolated environment
- Supports specifying package versions (e.g., `htop@3.3.0`)
- Verbose mode for detailed output
- Cache purging functionality

## Installation

1.  Clone the repository (or download the source):

    ```bash
    git clone https://github.com/anshtiwatne/yoink.git
    cd yoink
    ```

2.  Install using pip (this will also make the `yoink` command available):

    ```bash
    pip install .
    ```

    For development, you might prefer an editable install:
    ```bash
    pip install -e .
    ```

## Usage

```bash
yoink <package_spec>[@version] [command_args...]
```

## Examples

- Run `cowsay` with an argument:

    ```bash
    yoink cowsay "Moo from Yoink!"
    ```

- Run `sl` (System Locomotive):

    ```bash
    yoink sl
    ```

- Purge the cache:

    ```bash
    yoink --purge-cache
    ```
