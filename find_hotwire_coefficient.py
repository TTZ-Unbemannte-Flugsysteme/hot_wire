"""
Fit the hot-wire calibration coefficients from wind tunnel measurements and save them as
the calibration file of the sensor:  sensor_coefficients/<sensor serial number>.json

What this script does:
    1. Loads all CSV files in  calibration_data/<sensor serial number>/
       The wind tunnel speed is read from the file name, e.g. "..._15ms.csv" = 15 m/s.
    2. Fits the hot-wire formula of the SVMtec manual (see function 'model') to voltage vs. speed.
       Only a, b and e are fitted. m and Uoffset come from sensor_coefficients/daq_inputs.json, Ts is a
       fixed setting. Every 2nd sample is used for fitting ("training"), the rest for checking ("test").
    3. Calculates error margins: standard errors of a, b and e, a "leave one speed out" check,
       and the velocity error at every speed.
    4. Saves the result in sensor_coefficients/<sensor>.json together with a description of the data
       (file names, speeds, numbers of samples, SHA-256 hashes). An older calibration file of
        the sensor is first copied to sensor_coefficients/archive/. read_hotwire.py then uses the new file.
    5. Plots the fit (with the error vs. voltage) and the residuals.

Settings: user_settings.local.json, or user_settings.json, section "calibration_fit" (see README.md).

Requirements: numpy, pandas, scipy, matplotlib
"""

import platform
import re
import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy.optimize import curve_fit

from calibration_file import (CALIBRATION_DATA_DIR, DAQ_INPUTS_FILE, FORMAT_VERSION, FORMULA_ID, HASH_METHOD,
                              FORMULA_TEXT, combined_sha256, file_sha256, load_daq_input,
                              read_json, save_calibration)
from hotwire_model import voltage_to_velocity
from settings_file import PROJECT_DIR, load_settings, settings_path, values_in_order


# =============================================================================
# USER SETTINGS: section "calibration_fit", see README.md
# =============================================================================

PARAMETER_NAMES = ["a", "b", "e"]   # The fitted coefficients, in this order
MANUAL_FILE = PROJECT_DIR / "docs" / "Hitzdraht_doku.pdf"   # Source of the formula (its hash is stored)


def configure(settings=None):
    """Load settings only when running a fit, so importing helpers has no side effects."""
    global SETTINGS, BRIDGE_SENSOR_SN, MEASUREMENT_COLUMN, FLUID_TEMPERATURE
    global SAVE_CALIBRATION, CALIBRATION_NOTE, N_ERROR_BINS, SENSOR_TEMPERATURE
    global INITIAL_GUESS, LOWER_BOUNDS, UPPER_BOUNDS, DATA_DIR, DAQ_INPUT
    SETTINGS = load_settings("calibration_fit") if settings is None else settings
    BRIDGE_SENSOR_SN = SETTINGS["sensor"]
    MEASUREMENT_COLUMN = SETTINGS["voltage_column"]
    FLUID_TEMPERATURE = SETTINGS["air_temperature_C"]
    SAVE_CALIBRATION = SETTINGS["save_calibration"]
    CALIBRATION_NOTE = SETTINGS["calibration_note"]
    N_ERROR_BINS = SETTINGS["plot_error_bins"]
    SENSOR_TEMPERATURE = SETTINGS["sensor_temperatures_C"].get(BRIDGE_SENSOR_SN)
    INITIAL_GUESS = values_in_order(SETTINGS, "initial_guess", PARAMETER_NAMES)
    LOWER_BOUNDS = values_in_order(SETTINGS, "lower_bounds", PARAMETER_NAMES)
    UPPER_BOUNDS = values_in_order(SETTINGS, "upper_bounds", PARAMETER_NAMES)
    DATA_DIR = CALIBRATION_DATA_DIR / BRIDGE_SENSOR_SN
    DAQ_INPUT = load_daq_input(MEASUREMENT_COLUMN)

# Short explanations that are stored with the statistics in the calibration file
STATISTICS_EXPLANATION = {
    "standard_error": "From the covariance matrix of the fit. It assumes that all samples are "
                      "independent, which they are not (neighbouring samples are similar), so it is "
                      "too small (optimistic).",
    "ci95": "95 % confidence interval: value +- 1.96 * standard_error.",
    "leave_one_speed_out_standard_error": "Spread of the coefficient when the fit is repeated with "
                                          "one speed left out at a time (jackknife). A more "
                                          "realistic error margin.",
    "correlation": "Correlation between the coefficients. Values close to +-1 mean that the errors "
                   "of a, b and e largely cancel each other in the velocity.",
    "per_speed": "Velocity error at every calibration speed, over all samples of that speed. "
                 "'without_this_speed' = result of a fit that did not use this speed.",
}


# =============================================================================
# MODEL AND FIT
# =============================================================================

def model(u_measured, a, b, e):
    """
    Hot-wire formula of the SVMtec manual (eq. 2 and 3): measured voltage -> air speed v [m/s].

        u_bridge = u_measured / m + Uoffset
        v        = (a + b * u_bridge^2 / (Ts - Tf)) ^ e

    m and Uoffset come from DAQ_INPUT, Ts = SENSOR_TEMPERATURE, Tf = FLUID_TEMPERATURE.
    Below zero flow (a + b * ... < 0) the formula has no solution, so v is set to 0.
    """
    coefficients = {"a": a, "b": b, "e": e, "m": DAQ_INPUT["m"],
                    "Uoffset": DAQ_INPUT["Uoffset"], "Ts": SENSOR_TEMPERATURE}
    return voltage_to_velocity(u_measured, coefficients, FLUID_TEMPERATURE, clip_negative=True)[0]


def fit_coefficients(u, w, start):
    """Fit a, b and e to the voltages u and speeds w. Returns the coefficients and their covariance."""
    return curve_fit(model, u, w, p0=start, bounds=(LOWER_BOUNDS, UPPER_BOUNDS), maxfev=200000)


# =============================================================================
# LOADING DATA
# =============================================================================

def relative_name(path):
    """Path relative to this folder (with / as separator), or the full path if it is outside."""
    try:
        return Path(path).resolve().relative_to(PROJECT_DIR).as_posix()
    except ValueError:
        return Path(path).as_posix()


def rounded(value, digits=6):
    """Round to 'digits' significant digits for the calibration file (None if not a finite number)."""
    if value is None or not np.isfinite(value):
        return None
    return float(f"{value:.{digits}g}")


def find_speed_files(directory):
    """
    Find all files named like '*_<speed>ms.csv' in 'directory'.

    Returns a dictionary {file path: speed in m/s}.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"Data folder not found: {directory}")

    pattern = re.compile(r"_(\d+(?:\.\d+)?)ms(?:_\d+)?\.csv$", re.IGNORECASE)
    files = {}
    for path in sorted(directory.glob("*.csv")):
        match = pattern.search(path.name)
        if match:
            files[path] = float(match.group(1))
        else:
            print(f"Skipping {path.name} (expected an ending such as '_15ms.csv', '_2.5ms.csv' or '_15ms_1.csv')")

    if not files:
        raise FileNotFoundError(f"No files named '*_<speed>ms.csv' found in: {directory}")
    return files


def load_measurements(files, column):
    """
    Read the voltage column of every file and describe each file for the calibration file.

    Returns:
        voltages_by_file:   {file path: 1D array of voltages}
        file_descriptions:  one dictionary per file (name, speed, samples, hash, voltage statistics)
    """
    voltages_by_file = {}
    file_descriptions = []
    for path, speed in files.items():
        metadata_path = path.with_suffix(".metadata.json")
        metadata = read_json(metadata_path) if metadata_path.is_file() else None
        if metadata is not None:
            if not isinstance(metadata, dict) or not isinstance(metadata.get("settings"), dict):
                raise ValueError(f"{metadata_path.name}: metadata must contain a settings object.")
            if metadata.get("status") not in {"complete", "stopped"}:
                raise ValueError(f"{path.name}: the recording did not finish cleanly; check its metadata before fitting.")
            if metadata.get("hash_method") != HASH_METHOD or metadata.get("csv_sha256") != file_sha256(path):
                raise ValueError(f"{path.name}: the CSV fingerprint does not match its recording metadata. Recover the original CSV before fitting.")
            recorded = metadata.get("settings", {})
            if (recorded.get("sensor") != BRIDGE_SENSOR_SN or metadata.get("hotwire_channel") != column or
                    recorded.get("air_temperature_C") != FLUID_TEMPERATURE):
                raise ValueError(f"{path.name}: recorded sensor, hot-wire channel or air temperature differs from calibration_fit settings.")
        try:
            df = pd.read_csv(path)
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as error:
            raise ValueError(f"Cannot read {path.name}: {error}") from None
        if column not in df.columns:
            raise ValueError(f"Column '{column}' not found in {path.name}. "
                             f"Available columns: {list(df.columns)}")

        try:
            raw_voltages = pd.to_numeric(df[column], errors="raise").to_numpy(dtype=float)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{path.name}: '{column}' must contain numeric voltage samples: {error}") from None
        voltages = raw_voltages[np.isfinite(raw_voltages)]
        discarded = len(raw_voltages) - len(voltages)
        if len(voltages) < 2:
            raise ValueError(f"{path.name}: at least two finite voltage samples are required.")
        if discarded:
            print(f"WARNING: discarded {discarded} non-finite voltage samples in {path.name}.")
        voltages_by_file[path] = voltages
        print(f"Loaded {path.name}: {len(voltages)} samples at {speed:g} m/s")

        file_descriptions.append({
            "file": relative_name(path),
            "speed_m_per_s": speed,
            "samples": len(voltages),
            "discarded_nonfinite_samples": discarded,
            "sha256": file_sha256(path),
            "voltage_mean_V": rounded(np.mean(voltages)),
            "voltage_std_V": rounded(np.std(voltages)),
            "voltage_min_V": rounded(np.min(voltages)),
            "voltage_max_V": rounded(np.max(voltages)),
            "first_timestamp": str(df["Timestamp"].iloc[0]) if "Timestamp" in df.columns else None,
            "duration_s": rounded(df["Runtime"].max(), 4) if "Runtime" in df.columns else None,
        })
        if metadata is not None:
            file_descriptions[-1].update(metadata_file=relative_name(metadata_path), metadata_sha256=file_sha256(metadata_path))
    return voltages_by_file, file_descriptions


def combine_files(files, voltages_by_file):
    """Put the data of all files after each other: one voltage array and one speed array."""
    all_voltages = []
    all_speeds = []
    for path, speed in files.items():
        voltages = voltages_by_file[path]
        all_voltages.append(voltages)
        all_speeds.append(np.full(len(voltages), speed))
    return np.concatenate(all_voltages), np.concatenate(all_speeds)


# =============================================================================
# CHECKS
# =============================================================================

def check_settings(lower, upper, guess):
    """Stop with a clear message if the settings do not make sense."""
    if SENSOR_TEMPERATURE is None:
        raise ValueError(f"No sensor temperature Ts for sensor {BRIDGE_SENSOR_SN}: add it to "
                         f'"sensor_temperatures_C" in {settings_path().name}.')
    if SENSOR_TEMPERATURE <= FLUID_TEMPERATURE:
        raise ValueError(f"The sensor temperature Ts ({SENSOR_TEMPERATURE} °C) must be higher than "
                         f'"air_temperature_C" ({FLUID_TEMPERATURE} °C) in {settings_path().name}.')

    for name, low, high, start in zip(PARAMETER_NAMES, lower, upper, guess):
        if low >= high:
            raise ValueError(f"Bounds for '{name}' are wrong: lower ({low}) >= upper ({high}). "
                             f'Change "lower_bounds" / "upper_bounds" in {settings_path().name}.')
        if not low <= start <= high:
            raise ValueError(f"Initial guess for '{name}' ({start}) is outside the bounds "
                             f'[{low}, {high}]. Change "initial_guess", "lower_bounds" or '
                             f'"upper_bounds" in {settings_path().name}.')


def warn_if_at_bounds(params, lower, upper):
    """A coefficient that ends exactly at a limit means the fit was stopped there: warn."""
    for name, value, low, high in zip(PARAMETER_NAMES, params, lower, upper):
        margin = 1e-6 * (high - low)
        if value - low < margin or high - value < margin:
            print(f"WARNING: '{name}' = {value:.6f} is at its search limit [{low}, {high}]. "
                  f'The result is probably not the best fit. Widen "lower_bounds" / '
                  f'"upper_bounds" in {settings_path().name}.')


# =============================================================================
# ERROR MARGINS
# =============================================================================

def compute_rmse(y_true, y_pred):
    """Root mean square error."""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def leave_one_speed_out(files, voltages_by_file, params):
    """
    Repeat the fit with one speed left out at a time ("jackknife").

    Returns one result per speed: the refitted a, b, e and the mean velocity that this fit
    predicts for the left-out speed (a speed it has not seen).
    """
    results = {}
    for speed in sorted(set(files.values())):
        held_out = [path for path in files if files[path] == speed]
        others = [path for path in files if files[path] != speed]
        u = np.concatenate([voltages_by_file[path] for path in others])
        w = np.concatenate([np.full(len(voltages_by_file[path]), files[path]) for path in others])
        refit, _ = fit_coefficients(u[::2], w[::2], params)
        voltage = np.concatenate([voltages_by_file[path] for path in held_out])
        predicted = float(np.mean(model(voltage, *refit)))
        results[speed] = {"params": refit, "predicted": predicted}
    return results


def calculate_statistics(params, covariance, files, voltages_by_file, u_train, w_train, u_test, w_test):
    """Error margins of the coefficients and of the velocity, as stored in the calibration file."""
    standard_errors = np.sqrt(np.diag(covariance))
    with np.errstate(invalid="ignore", divide="ignore"):
        correlation = covariance / np.outer(standard_errors, standard_errors)

    # Leave one speed out. Needs at least 4 speeds, because 3 coefficients are fitted.
    loo = leave_one_speed_out(files, voltages_by_file, params) if len(set(files.values())) >= 4 else {}
    if loo:
        loo_params = np.array([result["params"] for result in loo.values()])
        n = len(loo)
        jackknife_errors = np.sqrt((n - 1) / n * np.sum((loo_params - loo_params.mean(axis=0)) ** 2, axis=0))
    else:
        jackknife_errors = [None] * len(PARAMETER_NAMES)

    coefficient_uncertainty = {}
    for i, name in enumerate(PARAMETER_NAMES):
        coefficient_uncertainty[name] = {
            "value": params[i],
            "standard_error": rounded(standard_errors[i]),
            "ci95": [rounded(params[i] - 1.96 * standard_errors[i]),
                     rounded(params[i] + 1.96 * standard_errors[i])],
            "leave_one_speed_out_standard_error": rounded(jackknife_errors[i]),
        }

    per_speed = []
    for speed in sorted(set(files.values())):
        voltages = np.concatenate([voltages_by_file[path] for path in files if files[path] == speed])
        predicted = model(voltages, *params)
        mean_fit = float(np.mean(predicted))
        without = loo[speed]["predicted"] if loo else None
        per_speed.append({
            "speed_m_per_s": speed,
            "samples": len(predicted),
            "mean_fit_m_per_s": rounded(mean_fit),
            "bias_m_per_s": rounded(mean_fit - speed),
            "bias_percent": rounded(100 * (mean_fit - speed) / speed) if speed > 0 else None,
            "rmse_m_per_s": rounded(compute_rmse(np.full(len(predicted), speed), predicted)),
            "mean_fit_without_this_speed_m_per_s": rounded(without),
            "error_without_this_speed_m_per_s": rounded(without - speed) if without is not None else None,
        })

    loo_fits = []
    for speed, result in loo.items():
        fit_result = {"left_out_speed_m_per_s": speed}
        for name, value in zip(PARAMETER_NAMES, result["params"]):
            fit_result[name] = rounded(value)
        loo_fits.append(fit_result)

    return {
        "rmse_training_m_per_s": rounded(compute_rmse(w_train, model(u_train, *params))),
        "rmse_test_m_per_s": rounded(compute_rmse(w_test, model(u_test, *params))),
        "coefficient_uncertainty": coefficient_uncertainty,
        "correlation": {"a_b": rounded(correlation[0, 1]), "a_e": rounded(correlation[0, 2]),
                        "b_e": rounded(correlation[1, 2])},
        "per_speed": per_speed,
        "leave_one_speed_out_fits": loo_fits,
        "explanation": STATISTICS_EXPLANATION,
    }


def show(value, decimals):
    """Number as text for the printed tables, or '-' if there is no value."""
    return "-" if value is None else f"{value:.{decimals}f}"


def print_results(params, statistics):
    """Print the coefficients with their error margins and the velocity error per speed."""
    print("\nFitted coefficients with error margins:")
    print(f"{'':6s}{'value':>12s}{'std. error':>13s}{'leave one speed out':>21s}")
    for name, value in zip(PARAMETER_NAMES, params):
        uncertainty = statistics["coefficient_uncertainty"][name]
        print(f"{name:6s}{value:>12.6f}{show(uncertainty['standard_error'], 6):>13s}"
              f"{show(uncertainty['leave_one_speed_out_standard_error'], 6):>21s}")

    print(f"\nRMSE: training data {statistics['rmse_training_m_per_s']:.4f} m/s, "
          f"test data {statistics['rmse_test_m_per_s']:.4f} m/s")

    print("\nVelocity error per speed [m/s]:")
    print(f"{'speed':>7s}{'samples':>9s}{'mean fit':>10s}{'bias':>9s}{'RMSE':>8s}{'error without this speed':>26s}")
    for row in statistics["per_speed"]:
        print(f"{row['speed_m_per_s']:>7g}{row['samples']:>9d}{show(row['mean_fit_m_per_s'], 3):>10s}"
              f"{show(row['bias_m_per_s'], 3):>9s}{show(row['rmse_m_per_s'], 3):>8s}"
              f"{show(row['error_without_this_speed_m_per_s'], 3):>26s}")


# =============================================================================
# CALIBRATION FILE
# =============================================================================

def build_calibration(coefficients, statistics, file_descriptions, n_train, n_test):
    """Put everything that belongs to this calibration into one dictionary (the JSON file)."""
    speeds = [f["speed_m_per_s"] for f in file_descriptions]
    return {
        "format_version": FORMAT_VERSION,
        "sensor": BRIDGE_SENSOR_SN,
        "created": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "formula": FORMULA_ID,
        "formula_text": FORMULA_TEXT,
        "coefficients": coefficients,
        "fit": {
            "script": Path(__file__).name,
            "script_sha256": file_sha256(__file__),
            "hash_method": HASH_METHOD,
            "model_script": "hotwire_model.py",
            "model_script_sha256": file_sha256(PROJECT_DIR / "hotwire_model.py"),
            "method": "scipy.optimize.curve_fit (bounded least squares on the velocity)",
            "fitted_coefficients": PARAMETER_NAMES,
            "fixed_coefficients": {
                "m": f"input {MEASUREMENT_COLUMN} in {relative_name(DAQ_INPUTS_FILE)}",
                "Uoffset": f"input {MEASUREMENT_COLUMN} in {relative_name(DAQ_INPUTS_FILE)}",
                "Ts": "sensor_temperatures_C in the settings file (cannot be fitted from data at one "
                      "air temperature)",
            },
            "fluid_temperature_C": FLUID_TEMPERATURE,
            "settings": SETTINGS,
            "settings_file": settings_path().name,
            "initial_guess": INITIAL_GUESS,
            "lower_bounds": LOWER_BOUNDS,
            "upper_bounds": UPPER_BOUNDS,
            "training_samples": n_train,
            "test_samples": n_test,
            "split": "training = every 2nd sample (even sample numbers), test = the remaining samples",
        },
        "source_data": {
            "hash_method": HASH_METHOD,
            "description": "Wind tunnel recordings. The reference speed is the nominal tunnel speed "
                           "in the file name (..._<speed>ms.csv).",
            "folder": relative_name(DATA_DIR),
            "voltage_column": MEASUREMENT_COLUMN,
            "number_of_files": len(file_descriptions),
            "number_of_speeds": len(set(speeds)),
            "total_samples": sum(f["samples"] for f in file_descriptions),
            "speed_range_m_per_s": [min(speeds), max(speeds)],
            "voltage_range_V": [min(f["voltage_min_V"] for f in file_descriptions),
                                max(f["voltage_max_V"] for f in file_descriptions)],
            "dataset_sha256": combined_sha256([(f["file"], f["sha256"]) for f in file_descriptions]),
            "files": file_descriptions,
            "other_sources": [
                {"file": relative_name(DAQ_INPUTS_FILE), "sha256": file_sha256(DAQ_INPUTS_FILE),
                 "used_for": f"m and Uoffset of input {MEASUREMENT_COLUMN}"},
                {"file": relative_name(MANUAL_FILE),
                 "sha256": file_sha256(MANUAL_FILE) if MANUAL_FILE.is_file() else None,
                 "used_for": "formula (section 6.5, eq. 2 and 3)"},
            ],
        },
        "statistics": statistics,
        "software": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "pandas": pd.__version__},
        "notes": [CALIBRATION_NOTE] if CALIBRATION_NOTE else [],
    }


# =============================================================================
# PLOTS
# =============================================================================

def plot_residuals(u_measured, w_true, params):
    """Plot the error (measured speed - model speed) of every sample."""
    residuals = w_true - model(u_measured, *params)

    plt.figure(figsize=(12, 4))
    plt.scatter(u_measured, residuals, s=10)
    plt.axhline(0, linestyle="--")
    plt.xlabel("Voltage (V)")
    plt.ylabel("Residual (m/s)")
    plt.title("Residuals: w_true - w_pred")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.show()


def plot_fit_with_error_axis(u_train, w_train, u_test, w_test, params, n_bins=None):
    """
    Left axis: training/test data and the fitted curve.
    Right axis (red): mean absolute error of the test data vs. voltage.
    """
    n_bins = N_ERROR_BINS if n_bins is None else n_bins
    fig, ax1 = plt.subplots(figsize=(12, 5))

    ax1.scatter(u_train, w_train, s=20, label="Training data (every 2nd sample)", alpha=0.7)
    ax1.scatter(u_test, w_test, s=20, label="Test data (remaining samples)", alpha=0.7)

    u_curve = np.linspace(np.min(u_train), np.max(u_train), 500)
    ax1.plot(u_curve, model(u_curve, *params), linewidth=2, label="Fitted model")

    ax1.set_xlabel("Voltage (V)")
    ax1.set_ylabel("Speed (m/s)")
    ax1.set_title(f"Curve fit: speed vs. voltage, sensor {BRIDGE_SENSOR_SN}")
    ax1.grid(True, linestyle="--", alpha=0.4)

    # --- Mean absolute error per voltage bin ---
    abs_err = np.abs(w_test - model(u_test, *params))

    bin_edges = np.linspace(np.min(u_test), np.max(u_test), n_bins + 1)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    bin_index = np.clip(np.digitize(u_test, bin_edges) - 1, 0, n_bins - 1)

    mae_per_bin = np.full(n_bins, np.nan)
    for i in range(n_bins):
        in_bin = bin_index == i
        if np.any(in_bin):
            mae_per_bin[i] = np.mean(abs_err[in_bin])

    ax2 = ax1.twinx()
    valid = ~np.isnan(mae_per_bin)
    ax2.plot(bin_centers[valid], mae_per_bin[valid], linewidth=2, label="Mean |error| (test)", color="red")
    ax2.set_ylabel("Mean |error| (m/s)")

    # One legend for both axes
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="best")

    fig.tight_layout()
    plt.show()


# =============================================================================
# MAIN PROGRAM
# =============================================================================

def main(show_plots=True):
    # 1. Check the settings and load the data
    configure()
    print(f"Settings: {settings_path().name}; save_calibration = {SAVE_CALIBRATION}")
    check_settings(LOWER_BOUNDS, UPPER_BOUNDS, INITIAL_GUESS)
    files = find_speed_files(DATA_DIR)
    if len(set(files.values())) < 3:
        raise ValueError("At least three distinct wind tunnel speeds are required to fit a, b and e; use four or more for the leave-one-speed-out check.")
    voltages_by_file, file_descriptions = load_measurements(files, MEASUREMENT_COLUMN)
    u_measured, w = combine_files(files, voltages_by_file)

    print(f"\nFixed values: m = {DAQ_INPUT['m']}, Uoffset = {DAQ_INPUT['Uoffset']} V "
          f"(input {MEASUREMENT_COLUMN}), Ts = {SENSOR_TEMPERATURE} °C, Tf = {FLUID_TEMPERATURE} °C")

    # 2. Split the data: even samples for fitting, odd samples for checking
    u_train, w_train = u_measured[::2], w[::2]
    u_test, w_test = u_measured[1::2], w[1::2]

    # 3. Fit a, b and e. They are rounded to 6 decimals, exactly as stored in the calibration file.
    fitted, covariance = fit_coefficients(u_train, w_train, INITIAL_GUESS)
    warn_if_at_bounds(fitted, LOWER_BOUNDS, UPPER_BOUNDS)
    params = [round(float(value), 6) for value in fitted]

    # 4. Error margins
    statistics = calculate_statistics(params, covariance, files, voltages_by_file,
                                      u_train, w_train, u_test, w_test)
    print_results(params, statistics)

    # 5. Save the calibration file
    if SAVE_CALIBRATION:
        coefficients = dict(zip(PARAMETER_NAMES, params))
        coefficients.update({"m": DAQ_INPUT["m"], "Uoffset": DAQ_INPUT["Uoffset"], "Ts": SENSOR_TEMPERATURE})
        calibration = build_calibration(coefficients, statistics, file_descriptions, len(u_train), len(u_test))
        path, archived = save_calibration(BRIDGE_SENSOR_SN, calibration)
        print(f"\nSaved the calibration file {relative_name(path)}")
        if archived:
            print(f"The previous calibration file was moved to {relative_name(archived)}")
    else:
        print('\n"save_calibration" is false: no calibration file was written.')

    # 6. Plots
    if show_plots:
        plot_fit_with_error_axis(u_train, w_train, u_test, w_test, params)
        plot_residuals(u_measured, w, params)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fit a calibration from wind tunnel CSV files (settings in user_settings.local.json).")
    parser.add_argument("--no-plot", action="store_true", help="print results without opening plot windows")
    args = parser.parse_args()
    try:
        main(show_plots=not args.no_plot)
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"ERROR: {error}") from None
