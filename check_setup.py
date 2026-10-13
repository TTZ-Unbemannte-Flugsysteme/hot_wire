"""Check packages, settings, input files and output access without recording or fitting.

Run: python check_setup.py [--daq | --hardware]
Temporary files are used to test writes; existing results and calibrations are unchanged.
"""

import argparse
import ast
import contextlib
import importlib
import importlib.metadata
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from install_ni_driver import is_wsl

PROJECT_DIR = Path(__file__).resolve().parent
SCRIPT_NAMES = (
    "analyse_example.py", "find_hotwire_coefficient.py", "read_hotwire.py",
    "hotwire_model.py", "calibration_file.py", "settings_file.py", "check_setup.py", "install_ni_driver.py",
)
STATUS_COLORS = {"OK": "\033[32m", "WARN": "\033[38;5;208m", "ERROR": "\033[31m"}


def enable_status_colors():
    """Enable terminal colours, keeping redirected reports plain text."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    if os.name != "nt":
        return True
    # Command Prompt needs virtual-terminal processing enabled for ANSI colours.
    try:
        import ctypes
        from ctypes import wintypes
        console = ctypes.WinDLL("kernel32", use_last_error=True)
        console.GetStdHandle.argtypes = [wintypes.DWORD]
        console.GetStdHandle.restype = wintypes.HANDLE
        console.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        console.GetConsoleMode.restype = wintypes.BOOL
        console.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        console.SetConsoleMode.restype = wintypes.BOOL
        handle = console.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = wintypes.DWORD()
        if not console.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(console.SetConsoleMode(handle, mode.value | 0x0005))
    except (AttributeError, OSError):
        return False


class Report:
    """Collect failures so one problem does not hide the remaining checks."""

    def __init__(self):
        self.entries = []
        self.use_color = enable_status_colors()

    def add(self, level, message):
        self.entries.append((level, message))
        label = f"[{level}]"
        if self.use_color and level in STATUS_COLORS:
            label = f"{STATUS_COLORS[level]}{label}\033[39m"
        print(f"{label} {str(message).replace(chr(10), chr(10) + '       ')}")

    def run(self, label, action, *, failure="ERROR", fix=""):
        try:
            result = action()
        except Exception as error:
            self.add(failure, f"{label}: {error}" + (f"\nFix: {fix}" if fix else ""))
            return None
        self.add("OK", label)
        return result

    def finish(self):
        errors = sum(level == "ERROR" for level, _ in self.entries)
        warnings = sum(level == "WARN" for level, _ in self.entries)
        print(f"\nCheck finished: {errors} error(s), {warnings} warning(s).")
        if errors:
            print("Fix the errors above, then run this check again. See README.md.")
        else:
            print("All required checks passed. Review any warnings above.")
        return 1 if errors else 0


def probe_directory(directory):
    """Exercise create/write/flush/read/replace/delete, then remove our test files.

    Missing folders are created for the test and removed again if still empty.
    Unique temporary names prevent overwriting students' files.
    """
    directory = Path(directory)
    created, temporary = [], []
    pending = []
    ancestor = directory
    while not ancestor.exists():
        pending.append(ancestor)
        ancestor = ancestor.parent
    try:
        for path in reversed(pending):
            try:
                path.mkdir()
                created.append(path)
            except FileExistsError:
                pass  # Another process may have created it in the meantime.
        payload = b"Hot-wire setup write test\n"
        for content in (payload, b"replacement test\n"):
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".hotwire-check-", delete=False) as stream:
                path = Path(stream.name)
                temporary.append(path)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        if temporary[0].read_bytes() != payload:
            raise OSError("The temporary file could not be read back correctly.")
        temporary[0].replace(temporary[1])
        if temporary[1].read_bytes() != payload:
            raise OSError("The temporary file could not be replaced correctly.")
    finally:
        try:
            for path in temporary:
                path.unlink(missing_ok=True)
        finally:
            for path in reversed(created):
                try:
                    path.rmdir()
                except OSError:
                    if path.exists() and not any(path.iterdir()):
                        raise
                    # Leave a folder that another process has started using.


def probe_editable_file(path):
    """Open for writing without changing a byte."""
    with Path(path).open("r+b"):
        pass


def requirement_lines(path, seen=None):
    seen = set() if seen is None else seen
    path = Path(path).resolve()
    if path in seen:
        raise ValueError(f"Repeated requirements include: {path}")
    seen.add(path)
    lines = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("-r "):
            lines.extend(requirement_lines(path.parent / line[3:].strip(), seen))
        elif line:
            lines.append(line)
    return lines


def check_dependency(line, requirement_type):
    requirement = requirement_type(line) if requirement_type else None
    name = requirement.name if requirement else re.match(r"[\w.-]+", line).group()
    if requirement and requirement.marker and not requirement.marker.evaluate():
        return "not required on this platform"
    version = importlib.metadata.version(name)
    if requirement and not requirement.specifier.contains(version, prereleases=True):
        raise ValueError(f"{name} {version} is installed; this project requires {line}.")
    importlib.import_module(name.replace("-", "_"))
    return version


def check_pip():
    result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True,
                            text=True, timeout=30)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).strip())
    return True


def check_packages(report, daq):
    lines = report.run("Read package requirements", lambda: requirement_lines(
        PROJECT_DIR / ("requirements-daq.txt" if daq else "requirements.txt")))
    parser = report.run("Package version checker", lambda: importlib.import_module("packaging.requirements").Requirement,
                        fix="Rerun the setup helper to install packaging.")
    installed = {}
    for line in lines or []:
        version = report.run(f"Package {line} (version and import)", lambda line=line: check_dependency(line, parser),
                             fix="Use the activation helper and rerun setup; add daq for nidaqmx.")
        name = re.match(r"[\w.-]+", line)
        if name and version is not None:
            installed[name.group()] = version
            print(f"       Installed: {version}")
    report.run("Installed packages have compatible dependencies (pip check)", check_pip,
               fix="Rerun setup. If conflicts remain, recreate .venv as described in README.md.")
    return installed


def check_measurement_configuration(settings):
    calibration = importlib.import_module("calibration_file").load_calibration(settings["sensor"])
    channels = importlib.import_module("settings_file").expand_channels(settings["daq_channels"])
    channel = channels[settings["hotwire_channel_index"]]
    importlib.import_module("read_hotwire").check_calibration_channel(calibration, channel)
    importlib.import_module("hotwire_model").validate_conversion(calibration["coefficients"], settings["air_temperature_C"])
    return True


def check_fit_data(report, settings):
    fit = report.run("Load calibration analysis script", lambda: importlib.import_module("find_hotwire_coefficient"))
    if fit is None:
        return
    configured = report.run("Calibration fit settings and DAQ conversion", lambda: (fit.configure(settings), True)[1])
    if not configured:
        return
    files = report.run(f"Calibration CSV folder: {fit.DATA_DIR}", lambda: fit.find_speed_files(fit.DATA_DIR))
    if not files:
        return
    if len(set(files.values())) < 3:
        report.add("ERROR", "Calibration fitting requires at least three distinct speeds in the filenames.")
    for path, speed in files.items():
        def read_data():
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                fit.load_measurements({path: speed}, settings["voltage_column"])
            for line in output.getvalue().splitlines():
                if line.startswith("WARNING:"):
                    report.add("WARN", line.removeprefix("WARNING:").strip())
            return True
        report.run(f"Read calibration CSV and any metadata: {path.name}", read_data)
    report.run("Read formula manual used in saved calibrations", lambda: fit.MANUAL_FILE.read_bytes())


def check_plotting():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    figure = Figure()
    figure.subplots().plot([0, 1], [0, 1])
    FigureCanvasAgg(figure).print_png(io.BytesIO())
    return True


def check_hardware(report, settings, *, strict):
    failure = "ERROR" if strict else "WARN"
    if is_wsl():
        report.add(failure, "WSL detected: hardware acquisition is not a supported workflow in this project.\n"
                   "Use a Windows checkout or a supported native Linux measurement PC for recording.\n"
                   "Analysis and calibration exercises can run in WSL. See README.md.")
        return
    fix = ("Run python install_ni_driver.py on the measurement PC after setup with daq. "
           "Linux installation needs administrator access; the helper requests sudo. "
           "Connect the DAQ and check its device name/channels with NI's configuration tools. See README.md.")
    system = report.run("NI-DAQmx driver access", lambda: importlib.import_module("nidaqmx.system").System.local(),
                        failure=failure, fix=fix)
    if system is None:
        return
    version = report.run("Read NI-DAQmx driver version", lambda: system.driver_version, failure=failure, fix=fix)
    if version is None:
        return
    print(f"       Driver: {version.major_version}.{version.minor_version}.{version.update_version}")
    if settings is None:
        report.add("SKIP", "Device/channel checks need valid read_hotwire settings.")
        return

    def device_channels():
        available = list(system.devices.device_names)
        name = settings["daq_device"]
        if name not in available:
            raise ValueError(f"Device {name!r} was not found. Available devices: {available or 'none'}.")
        device = system.devices[name]
        if device.dev_is_simulated:
            raise ValueError(f"{name} is a simulated device; select the connected laboratory DAQ.")
        physical = set(device.ai_physical_chans.channel_names)
        channels = importlib.import_module("settings_file").expand_channels(settings["daq_channels"])
        missing = [f"{name}/{channel}" for channel in channels if f"{name}/{channel}" not in physical]
        if missing:
            raise ValueError(f"Analog inputs not found: {missing}. Available: {sorted(physical)}.")
        return True
    report.run("Configured NI device and analog inputs exist", device_channels, failure=failure, fix=fix)


def check_environment(report):
    if Path(sys.prefix).resolve() == (PROJECT_DIR / ".venv").resolve():
        return True
    relative = ".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python"
    try:
        exists = (PROJECT_DIR / relative).is_file()
    except OSError as error:
        report.add("ERROR", f"Cannot access the project's Python environment: {error}")
        exists = False
    if sys.platform == "win32":
        command = "activate_venv.bat" if exists else "setup_venv.bat"
    else:
        command = "source ./activate_venv.sh" if exists else "source ./setup_venv.sh"
    report.add("ERROR", "This command is using Python outside this project's .venv.\n"
               f"From the project folder, run: {command}\nThen run: python check_setup.py\n"
               "Packages in system Python do not describe the project's installed packages.")
    report.add("SKIP", "Package and file checks were not run with the wrong Python environment.")
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daq", action="store_true", help="also require nidaqmx; report unavailable hardware as warnings")
    parser.add_argument("--hardware", action="store_true", help="also require the NI driver and configured physical DAQ/inputs")
    args = parser.parse_args(argv)
    report = Report()
    print(f"Checking project: {PROJECT_DIR}\nPython: {sys.executable}\n")
    report.add("OK" if sys.version_info >= (3, 10) else "ERROR", f"Python {sys.version.split()[0]} (requires 3.10 or newer)")
    if not check_environment(report):
        return report.finish()
    installed = check_packages(report, args.daq or args.hardware)
    for name in SCRIPT_NAMES:
        report.run(f"Read Python script and check syntax: {name}",
                   lambda name=name: ast.parse((PROJECT_DIR / name).read_text(encoding="utf-8-sig"), filename=name),
                   fix="Recover the named file from the project download, or check your edits.")
    settings_module = report.run("Load settings helper", lambda: importlib.import_module("settings_file"))
    recording_settings = fit_settings = None
    if settings_module is not None:
        report.add("OK", f"Selected settings file: {settings_module.settings_path()}")
        recording_settings = report.run("Read and validate read_hotwire settings", lambda: settings_module.load_settings("read_hotwire"))
        fit_settings = report.run("Read and validate calibration_fit settings", lambda: settings_module.load_settings("calibration_fit"))
        if settings_module.LOCAL_SETTINGS_FILE.exists():
            report.run("Local settings can be edited", lambda: probe_editable_file(settings_module.LOCAL_SETTINGS_FILE), failure="WARN",
                       fix="Move the project to a writable local folder or ask your instructor about folder permissions.")
    if recording_settings is not None:
        directory = PROJECT_DIR / recording_settings["output_folder"]
        report.run(f"Read/write/replace/delete recording files in: {directory}", lambda: probe_directory(directory),
                   fix="Choose a writable output_folder inside this project, or move the project to a writable folder.")
        if {"numpy", "matplotlib"} <= installed.keys():
            report.run("Read active measurement calibration; check channel, gain/offset and temperature",
                       lambda: check_measurement_configuration(recording_settings), fix="Check read_hotwire settings and the calibration. See README.md.")
        else:
            report.add("SKIP", "Measurement calibration checks need the missing analysis packages.")
    if fit_settings is not None:
        failure = "ERROR" if fit_settings["save_calibration"] else "WARN"
        for folder in (PROJECT_DIR / "sensor_coefficients", PROJECT_DIR / "sensor_coefficients" / "archive"):
            report.run(f"Read/write/replace/delete calibration files in: {folder}", lambda folder=folder: probe_directory(folder),
                       failure=failure, fix="Use a writable project folder before enabling save_calibration.")
        active = PROJECT_DIR / "sensor_coefficients" / f"{fit_settings['sensor']}.json"
        if active.exists():
            report.run("Active fit calibration file can be opened for writing", lambda: probe_editable_file(active), failure=failure)
        if {"numpy", "pandas", "scipy", "matplotlib"} <= installed.keys():
            check_fit_data(report, fit_settings)
        else:
            report.add("SKIP", "Calibration CSV checks need the missing analysis packages.")
    if {"numpy", "pandas", "matplotlib"} <= installed.keys():
        def example():
            with contextlib.redirect_stdout(io.StringIO()):
                importlib.import_module("analyse_example").main(show_plot=False)
            return True
        report.run("Read and analyse the supplied example (no plot or saved results)", example)
    if "matplotlib" in installed:
        report.run("Render a test plot in memory", check_plotting)
        backend = importlib.import_module("matplotlib").get_backend()
        report.add("OK", f"Matplotlib backend: {backend}")
        if backend.lower() in {"agg", "pdf", "ps", "svg", "pgf", "cairo", "template"}:
            report.add("WARN", "This plotting backend does not open plot windows. Use --no-plot for the exercises or install a GUI backend.")
    if args.daq or args.hardware:
        if "nidaqmx" in installed:
            check_hardware(report, recording_settings, strict=args.hardware)
        else:
            report.add("SKIP", "NI driver/device checks need nidaqmx. Rerun setup with daq.")
        print("\nHardware checks read device information only. They do not test sensor wiring or acquire samples.")
    else:
        report.add("SKIP", "NI driver/device checks: use python check_setup.py --hardware on the laboratory PC.")
    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
