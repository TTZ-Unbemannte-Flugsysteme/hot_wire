"""Launch NI's system-driver installer using this project's Python environment.

Run only on the measurement PC: python install_ni_driver.py
Linux installation requests sudo; Windows uses NI's installer elevation prompt.
Use --dry-run to check prerequisites and print the command without installing.
"""

import argparse
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys

PROJECT_DIR = Path(__file__).resolve().parent


def is_wsl():
    return sys.platform.startswith("linux") and (
        "microsoft" in platform.release().lower() or "wsl" in platform.release().lower()
        or bool(os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"))
    )


def setup_command():
    return "setup_venv.bat daq" if sys.platform == "win32" else "source ./setup_venv.sh daq"


def installer_command():
    """Validate the target and keep the venv interpreter when elevating on Linux."""
    if sys.platform not in {"win32", "linux"}:
        raise RuntimeError("NI driver installation requires Windows or a supported native Linux system. See README.md.")
    if is_wsl():
        raise RuntimeError(
            "WSL detected. This project's installer helper targets Windows or native Linux, not WSL.\n"
            "For recording on this PC, set up a separate Windows checkout and install the driver there.\n"
            "WSL can still run the supplied analysis and calibration exercises. See README.md."
        )
    relative = ".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python"
    # Do not resolve this symlink: on Linux it would select system Python again.
    python = PROJECT_DIR / relative
    if not python.is_file():
        raise RuntimeError(f"The project's Python environment is missing. From the project folder, run: {setup_command()}")
    result = subprocess.run([str(python), "-c", "import nidaqmx"], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"The DAQ Python package is missing or broken in .venv. Run: {setup_command()}\n"
                           f"{(result.stdout + result.stderr).strip()}")
    command = [str(python), "-m", "nidaqmx", "installdriver"]
    if sys.platform == "linux" and os.geteuid() != 0:
        sudo = shutil.which("sudo")
        if sudo is None:
            raise RuntimeError("Linux driver installation needs administrator access, but sudo was not found. Ask your instructor/IT.")
        command = [sudo, "--", *command]
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="check prerequisites and print the command without installing")
    args = parser.parse_args(argv)
    try:
        command = installer_command()
        print("NI-DAQmx is a system driver, separate from the Python packages in .venv.")
        if sys.platform == "linux":
            print("Installation needs administrator access. sudo may ask for your Linux password.")
        print("Installer command:", subprocess.list2cmdline(command) if sys.platform == "win32" else shlex.join(command), flush=True)
        if args.dry_run:
            print("Dry run: the driver installer was not started.")
            return 0
        result = subprocess.run(command)
        if result.returncode:
            print(f"ERROR: The NI installer returned exit code {result.returncode}. Review its messages above.\n"
                  "If administrator access was denied, ask your instructor/IT.\n"
                  "An apt lock held by another process means another package manager is running; let it finish.\n"
                  "Do not delete lock files or run the project's Python package setup with sudo.", file=sys.stderr)
            return 1
        print("Installer command completed. Follow any NI reboot instructions, then run: python check_setup.py --hardware")
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDriver installer interrupted. Check its messages before trying again.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
