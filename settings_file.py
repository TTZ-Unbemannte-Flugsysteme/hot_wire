"""
Reading the user settings (user_settings.local.json, or user_settings.json).

This is a helper module. It is used by read_hotwire.py, find_hotwire_coefficient.py. It is not run on its own.

user_settings.json has one section per task (every setting is explained in README.md):
    read_hotwire       recording with the NI DAQ (read_hotwire.py)
    calibration_fit    fitting a calibration (find_hotwire_coefficient.py)
Keys that start with "_" are comments and are ignored.

Every section is checked completely: a missing, misspelled or unknown setting, or a value of
the wrong type, stops the script with a clear message, so that a typo is never ignored.
"""

import json
import math
import re
from pathlib import Path, PureWindowsPath

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_SETTINGS_FILE = PROJECT_DIR / "user_settings.json"
LOCAL_SETTINGS_FILE = PROJECT_DIR / "user_settings.local.json"

# The settings of every section and the type of their value.
# "number" = whole or decimal number, "numbers" = {"name": number, ...}
SECTIONS = {
    "read_hotwire": {
        "sensor": str,
        "test_label": str,
        "air_temperature_C": "number",
        "measurement_time_s": "number",
        "sample_rate_Hz": "number",
        "output_folder": str,
        "daq_device": str,
        "daq_channels": str,
        "hotwire_channel_index": int,
        "show_plot": bool,
    },
    "calibration_fit": {
        "sensor": str,
        "voltage_column": str,
        "air_temperature_C": "number",
        "sensor_temperatures_C": "numbers",
        "save_calibration": bool,
        "calibration_note": str,
        "initial_guess": "numbers",
        "lower_bounds": "numbers",
        "upper_bounds": "numbers",
        "plot_error_bins": int,
    },
}

TYPE_NAMES = {str: 'a text in "double quotes"', bool: "true or false", int: "a whole number",
              "number": "a number", "numbers": '{"name": number, ...}'}

# Typical mistakes when editing JSON by hand, recognised from the error message of the json module
SYNTAX_HINTS = {
    "Invalid \\escape": "In folder paths, write / instead of \\.",
    "Illegal trailing comma before end of object": "Remove the comma after the last setting of the section.",
    "Expecting property name enclosed in double quotes":
        'Is there a comma after the last setting of a section? Names need "double quotes".',
    "Expecting ',' delimiter": "Is a comma missing at the end of the line before?",
    "Expecting value": 'Text needs "double quotes", and true / false are written in lower case.',
}


def is_number(value):
    """True for finite numbers, but not for true/false or NaN/infinity."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def has_type(value, kind):
    """True if 'value' has the type 'kind' of SECTIONS."""
    if kind == "number":
        return is_number(value)
    if kind == "numbers":
        return isinstance(value, dict) and all(is_number(v) for v in value.values())
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def settings_path():
    """Prefer the student's complete local copy; otherwise use the shared defaults."""
    return LOCAL_SETTINGS_FILE if LOCAL_SETTINGS_FILE.is_file() else DEFAULT_SETTINGS_FILE


def read_settings_file():
    """Read user_settings.json. A syntax error is reported with its line, column and a hint."""
    path = settings_path()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise FileNotFoundError(f"The settings file is missing: {path}") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        hint = SYNTAX_HINTS.get(error.msg)
        raise ValueError(f"{path.name}, line {error.lineno}, column {error.colno}: "
                         f"{error.msg}." + (f" {hint}" if hint else "")) from None


def load_settings(section):
    """
    Read and check one section of user_settings.json.

    Returns a dictionary {setting: value}, without the comments (keys that start with "_").
    """
    content = read_settings_file()
    filename = settings_path().name
    if not isinstance(content, dict):
        raise ValueError(f"{filename}: settings must be a JSON object inside {{ ... }}.")
    unknown_sections = [name for name in content if name not in SECTIONS and not name.startswith("_")]
    if unknown_sections:
        raise ValueError(f"{filename}: unknown section(s) {unknown_sections}. "
                         f"Known sections: {list(SECTIONS)}")
    if section not in content:
        raise ValueError(f'{filename}: the section "{section}" is missing.')
    if not isinstance(content[section], dict):
        raise ValueError(f'{filename}: section "{section}" must be a JSON object inside {{ ... }}.')

    values = {key: value for key, value in content[section].items() if not key.startswith("_")}
    expected = SECTIONS[section]
    problems = []
    unknown = [key for key in values if key not in expected]
    missing = [key for key in expected if key not in values]
    if unknown:
        problems.append(f"unknown setting(s) {unknown}")
    if missing:
        problems.append(f"missing setting(s) {missing}")
    if problems:
        raise ValueError(f'{filename}, section "{section}": {" and ".join(problems)}. '
                         f"Known settings: {list(expected)}")

    for key, kind in expected.items():
        if not has_type(values[key], kind):
            raise ValueError(f'{filename}, section "{section}": "{key}" must be '
                             f"{TYPE_NAMES[kind]}, not {json.dumps(values[key])}.")
    validate_values(section, values)
    return values


def validate_filename_part(value, name):
    """Reject names that cannot be used in a filename on Windows, macOS and Linux."""
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)}
    if (not value.strip() or value.endswith((".", " ")) or
            re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value.split(".")[0].upper() in reserved):
        raise ValueError(f'{settings_path().name}: "{name}" must be a non-empty filename part; '
                         'avoid / \\ : * ? " < > |, reserved names, and trailing dots or spaces.')


def expand_channels(channel_text):
    """Expand ai1, ai1:3 or ai1, ai4, rejecting malformed or duplicate channels."""
    names = []
    for part in channel_text.split(","):
        match = re.fullmatch(r"ai(\d+)(?::(\d+))?", part.strip())
        if not match:
            raise ValueError('"daq_channels" must contain names like "ai1", "ai1:3" or "ai1, ai4".')
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) is not None else first
        if last < first:
            raise ValueError('"daq_channels": a channel range must go from a lower to a higher number.')
        names.extend(f"ai{i}" for i in range(first, last + 1))
    if len(names) != len(set(names)):
        raise ValueError('"daq_channels" must not contain duplicate channels.')
    return names


def validate_values(section, values):
    """Check values students commonly mistype before acquisition or fitting starts."""
    validate_filename_part(values["sensor"], "sensor")
    if section == "read_hotwire":
        for key in ("measurement_time_s", "sample_rate_Hz"):
            if values[key] <= 0:
                raise ValueError(f'{settings_path().name}: "{key}" must be greater than zero.')
        validate_filename_part(values["test_label"], "test_label")
        folder = values["output_folder"]
        if not folder.strip() or "\\" in folder:
            raise ValueError('"output_folder" must be a relative folder path using / as the separator.')
        windows_path = PureWindowsPath(folder)
        if windows_path.is_absolute() or windows_path.drive or Path(folder).is_absolute() or ".." in Path(folder).parts:
            raise ValueError('"output_folder" must stay inside the project folder; do not use an absolute path or .. .')
        for part in Path(folder).parts:
            if part != ".":
                validate_filename_part(part, "output_folder")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", values["daq_device"]):
            raise ValueError('"daq_device" must be a device name such as "Dev1" (no spaces or slashes).')
        names = expand_channels(values["daq_channels"])
        if not 0 <= values["hotwire_channel_index"] < len(names):
            raise ValueError(f'"hotwire_channel_index" must be between 0 and {len(names) - 1} for {names}.')
    else:
        if values["plot_error_bins"] <= 0:
            raise ValueError('"plot_error_bins" must be greater than zero.')
        temperature = values["sensor_temperatures_C"].get(values["sensor"])
        if temperature is None or temperature <= values["air_temperature_C"]:
            raise ValueError('Add the selected sensor to "sensor_temperatures_C" with Ts higher than "air_temperature_C".')
        low = values_in_order(values, "lower_bounds", ["a", "b", "e"])
        high = values_in_order(values, "upper_bounds", ["a", "b", "e"])
        guess = values_in_order(values, "initial_guess", ["a", "b", "e"])
        for name, lower, upper, start in zip(("a", "b", "e"), low, high, guess):
            if lower >= upper or not lower <= start <= upper:
                raise ValueError(f'Check bounds and initial_guess for "{name}": lower < upper and lower <= guess <= upper are required.')
        if low[1] < 0 or low[2] <= 0:
            raise ValueError('The lower bound of b must be at least zero and the lower bound of e must be positive.')


def values_in_order(values, key, names):
    """
    Turn a setting like {"a": -0.665, "b": 105, "e": 2.42} into a list in the order of 'names',
    e.g. [-0.665, 105, 2.42]. Every name must be there exactly once.
    """
    given = values[key]
    if sorted(given) != sorted(names):
        raise ValueError(f'{settings_path().name}: "{key}" must contain exactly {list(names)}, '
                         f"not {list(given)}.")
    return [given[name] for name in names]
