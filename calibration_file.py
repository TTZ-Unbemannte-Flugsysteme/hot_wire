"""
Reading and writing the hot-wire calibration files (JSON).

This is a helper module. It is used by read_hotwire.py and the fit scripts and is not run on
its own.

Folder structure:
    sensor_coefficients/<sensor>.json     the active calibration of a sensor, e.g. sensor_coefficients/2025-6131.json
    sensor_coefficients/daq_inputs.json   gain m and offset Uoffset of the DAQ inputs (factory test report)
    sensor_coefficients/archive/          older calibration files, kept so that old results can be traced
    calibration_data/<sensor>/            the wind tunnel recordings that the calibrations are fitted from

A calibration file contains (see README.md for details):
    coefficients   a, b, e, m, Uoffset and Ts for the formula in FORMULA_TEXT
    fit            how the coefficients were fitted (script, fixed values, fit settings)
    source_data    the data that was used: file names, speeds, numbers of samples, SHA-256 hashes
    statistics     error margins of the coefficients and of the velocity
"""

import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

CALIBRATION_DIR = Path(__file__).resolve().parent / "sensor_coefficients"
CALIBRATION_DATA_DIR = Path(__file__).resolve().parent / "calibration_data"
ARCHIVE_DIR = CALIBRATION_DIR / "archive"
DAQ_INPUTS_FILE = CALIBRATION_DIR / "daq_inputs.json"

FORMAT_VERSION = 1
HASH_METHOD = "sha256-lf-v1"

# The formula the coefficients belong to. A calibration file made for another formula is
# refused, so that coefficients can never be used with the wrong formula.
FORMULA_ID = "svmtec_eq2"
FORMULA_TEXT = ("v = (a + b * U_br^2 / (Ts - Tf))^e  with  U_br = U_measured / m + Uoffset  "
                "(SVMtec manual Hitzdraht_doku.pdf, section 6.5, eq. 2 and 3)")
COEFFICIENT_NAMES = ["a", "b", "e", "m", "Uoffset", "Ts"]


def file_sha256(path):
    """
    SHA-256 fingerprint. Text line endings are normalised to LF; binary files
    such as PDFs are hashed unchanged. This works across operating systems.
    """
    path = Path(path)
    data = path.read_bytes()
    if path.suffix.lower() in {".csv", ".json", ".py", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


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
    """Replace a JSON file atomically, leaving the old file intact if writing fails."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            json.dump(content, f, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_calibration(sensor_sn):
    """
    Read and check the active calibration file of a sensor.

    Returns the whole content of the file as a dictionary.
    The coefficients are in calibration["coefficients"].
    """
    path = calibration_path(sensor_sn)
    if not path.is_file():
        available = sorted(p.stem for p in CALIBRATION_DIR.glob("*.json") if p.name != DAQ_INPUTS_FILE.name)
        raise FileNotFoundError(f"No calibration file for sensor '{sensor_sn}' ({path}).\n"
                                f"Sensors with a calibration file: {available}\n"
                                f"Make one with find_hotwire_coefficient.py.")

    calibration = read_json(path)
    if not isinstance(calibration, dict):
        raise ValueError(f"{path.name}: the calibration must be a JSON object.")
    if calibration.get("sensor") != sensor_sn:
        raise ValueError(f"{path.name}: the sensor number inside the file does not match '{sensor_sn}'.")
    if calibration.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"{path.name}: unknown format_version {calibration.get('format_version')}.")
    if calibration.get("formula") != FORMULA_ID:
        raise ValueError(f"{path.name} was made for the formula '{calibration.get('formula')}', "
                         f"but this code uses '{FORMULA_ID}'. Do not use these coefficients.")

    coefficients = calibration.get("coefficients") or {}
    if not isinstance(coefficients, dict):
        raise ValueError(f"{path.name}: coefficients must be a JSON object.")
    for name in COEFFICIENT_NAMES:
        value = coefficients.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"{path.name}: coefficient '{name}' is missing or not a finite number.")
    if coefficients["m"] <= 0 or coefficients["b"] < 0 or coefficients["e"] <= 0:
        raise ValueError(f"{path.name}: m and e must be positive, and b must be non-negative.")
    return calibration


def load_daq_input(input_name):
    """Gain m and offset Uoffset of one DAQ input (e.g. "ai1") from sensor_coefficients/daq_inputs.json."""
    inputs = read_json(DAQ_INPUTS_FILE)["inputs"]
    if input_name not in inputs:
        raise ValueError(f"Input '{input_name}' is not in {DAQ_INPUTS_FILE.name}. "
                         f"Known inputs: {list(inputs)}")
    conversion = inputs[input_name]
    for name in ("m", "Uoffset"):
        value = conversion.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"{DAQ_INPUTS_FILE.name}: {input_name}.{name} must be a finite number.")
    if conversion["m"] <= 0:
        raise ValueError(f"{DAQ_INPUTS_FILE.name}: {input_name}.m must be positive.")
    return conversion


def save_calibration(sensor_sn, calibration):
    """
    Save 'calibration' as the active calibration file of the sensor.
    Copy an existing file to a unique archive name, then replace it atomically.
    A failed save leaves the previous active calibration usable.

    Returns the path of the new file and the path of the archived file (or None).
    """
    path = calibration_path(sensor_sn)
    archived = None
    if path.exists():
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_name = f"{sensor_sn}_until_{datetime.now():%Y%m%d_%H%M%S_%f}"
        archived = ARCHIVE_DIR / f"{archive_name}.json"
        counter = 1
        while archived.exists():
            archived = ARCHIVE_DIR / f"{archive_name}_{counter}.json"
            counter += 1
        shutil.copy2(path, archived)

    CALIBRATION_DIR.mkdir(exist_ok=True)
    write_json(path, calibration)
    return path, archived
