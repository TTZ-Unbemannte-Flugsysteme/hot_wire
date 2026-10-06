"""
Reading the user settings (user_settings.json).

This is a helper module. It is used by read_hotwire.py, find_hotwire_coefficient.py and
optimization.py; it is not run on its own.

user_settings.json has one section per task (every setting is explained in README.md):
    read_hotwire       recording with the NI DAQ (read_hotwire.py)
    calibration_fit    fitting a calibration (find_hotwire_coefficient.py and optimization.py)
Keys that start with "_" are comments and are ignored.

Every section is checked completely: a missing, misspelled or unknown setting, or a value of
the wrong type, stops the script with a clear message, so that a typo is never ignored.
"""

import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = PROJECT_DIR / "user_settings.json"

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
    """True for whole and decimal numbers, but not for true/false (which Python counts as numbers)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def has_type(value, kind):
    """True if 'value' has the type 'kind' of SECTIONS."""
    if kind == "number":
        return is_number(value)
    if kind == "numbers":
        return isinstance(value, dict) and all(is_number(v) for v in value.values())
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def read_settings_file():
    """Read user_settings.json. A syntax error is reported with its line, column and a hint."""
    try:
        text = SETTINGS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"The settings file is missing: {SETTINGS_FILE}") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        hint = SYNTAX_HINTS.get(error.msg)
        raise ValueError(f"{SETTINGS_FILE.name}, line {error.lineno}, column {error.colno}: "
                         f"{error.msg}." + (f" {hint}" if hint else "")) from None


def load_settings(section):
    """
    Read and check one section of user_settings.json.

    Returns a dictionary {setting: value}, without the comments (keys that start with "_").
    """
    content = read_settings_file()
    unknown_sections = [name for name in content if name not in SECTIONS and not name.startswith("_")]
    if unknown_sections:
        raise ValueError(f"{SETTINGS_FILE.name}: unknown section(s) {unknown_sections}. "
                         f"Known sections: {list(SECTIONS)}")
    if section not in content:
        raise ValueError(f'{SETTINGS_FILE.name}: the section "{section}" is missing.')

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
        raise ValueError(f'{SETTINGS_FILE.name}, section "{section}": {" and ".join(problems)}. '
                         f"Known settings: {list(expected)}")

    for key, kind in expected.items():
        if not has_type(values[key], kind):
            raise ValueError(f'{SETTINGS_FILE.name}, section "{section}": "{key}" must be '
                             f"{TYPE_NAMES[kind]}, not {json.dumps(values[key])}.")
    return values


def values_in_order(values, key, names):
    """
    Turn a setting like {"a": -0.665, "b": 105, "e": 2.42} into a list in the order of 'names',
    e.g. [-0.665, 105, 2.42]. Every name must be there exactly once.
    """
    given = values[key]
    if sorted(given) != sorted(names):
        raise ValueError(f'{SETTINGS_FILE.name}: "{key}" must contain exactly {list(names)}, '
                         f"not {list(given)}.")
    return [given[name] for name in names]
