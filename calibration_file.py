"""
Reading and writing the hot-wire calibration files (JSON).

This is a helper module. It is used by read_hotwire.py, recompute_velocity.py and the fit
scripts; it is not run on its own.

Folder structure:
    calibration/<sensor>.json      the active calibration of a sensor, e.g. calibration/2025-6131.json
    calibration/daq_inputs.json    gain m and offset Uoffset of the DAQ inputs (factory test report)
    calibration/archive/           older calibration files, kept so that old results can be traced

A calibration file contains (see README.md for details):
    coefficients   a, b, e, m, Uoffset and Ts for the formula in FORMULA_TEXT
    fit            how the coefficients were fitted (script, fixed values, fit settings)
    source_data    the data that was used: file names, speeds, numbers of samples, SHA-256 hashes
    statistics     error margins of the coefficients and of the velocity
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

CALIBRATION_DIR = Path(__file__).resolve().parent / "calibration"
ARCHIVE_DIR = CALIBRATION_DIR / "archive"
DAQ_INPUTS_FILE = CALIBRATION_DIR / "daq_inputs.json"

FORMAT_VERSION = 1

# The formula the coefficients belong to. A calibration file made for another formula is
# refused, so that coefficients can never be used with the wrong formula.
FORMULA_ID = "svmtec_eq2"
FORMULA_TEXT = ("v = (a + b * U_br^2 / (Ts - Tf))^e  with  U_br = U_measured / m + Uoffset  "
                "(SVMtec manual Hitzdraht_doku.pdf, section 6.5, eq. 2 and 3)")
COEFFICIENT_NAMES = ["a", "b", "e", "m", "Uoffset", "Ts"]


def file_sha256(path):
    """
    SHA-256 hash of a file: a 64-character 'fingerprint' of its content.
    If even one byte of the file changes, the hash is completely different.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def combined_sha256(names_and_hashes):
    """One hash for a whole set of files, made from their names and their own hashes."""
    text = "\n".join(f"{name} {sha}" for name, sha in sorted(names_and_hashes))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def calibration_path(sensor_sn):
    """Path of the active calibration file of a sensor."""
    return CALIBRATION_DIR / f"{sensor_sn}.json"


def read_json(path):
    """Read a JSON file into a dictionary."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, content):
    """Write a dictionary to a JSON file (readable layout with 2 spaces indentation)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)
        f.write("\n")


def load_calibration(sensor_sn):
    """
    Read and check the active calibration file of a sensor.

    Returns the whole content of the file as a dictionary;
    the coefficients are in calibration["coefficients"].
    """
    path = calibration_path(sensor_sn)
    if not path.is_file():
        available = sorted(p.stem for p in CALIBRATION_DIR.glob("*.json") if p.name != DAQ_INPUTS_FILE.name)
        raise FileNotFoundError(f"No calibration file for sensor '{sensor_sn}' ({path}).\n"
                                f"Sensors with a calibration file: {available}\n"
                                f"Make one with find_hotwire_coefficient.py.")

    calibration = read_json(path)
    if calibration.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"{path.name}: unknown format_version {calibration.get('format_version')}.")
    if calibration.get("formula") != FORMULA_ID:
        raise ValueError(f"{path.name} was made for the formula '{calibration.get('formula')}', "
                         f"but this code uses '{FORMULA_ID}'. Do not use these coefficients.")

    coefficients = calibration.get("coefficients") or {}
    for name in COEFFICIENT_NAMES:
        value = coefficients.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{path.name}: coefficient '{name}' is missing or not a number.")
    return calibration


def load_daq_input(input_name):
    """Gain m and offset Uoffset of one DAQ input (e.g. "ai1") from calibration/daq_inputs.json."""
    inputs = read_json(DAQ_INPUTS_FILE)["inputs"]
    if input_name not in inputs:
        raise ValueError(f"Input '{input_name}' is not in {DAQ_INPUTS_FILE.name}. "
                         f"Known inputs: {list(inputs)}")
    return inputs[input_name]


def save_calibration(sensor_sn, calibration):
    """
    Save 'calibration' as the active calibration file of the sensor.
    An existing file is first moved to calibration/archive/, so no calibration is ever lost.

    Returns the path of the new file and the path of the archived file (or None).
    """
    path = calibration_path(sensor_sn)
    archived = None
    if path.exists():
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archived = ARCHIVE_DIR / f"{sensor_sn}_until_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.replace(archived)

    CALIBRATION_DIR.mkdir(exist_ok=True)
    write_json(path, calibration)
    return path, archived
