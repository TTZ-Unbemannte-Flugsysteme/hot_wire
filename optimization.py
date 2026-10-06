"""
Fit the hot-wire calibration coefficients from wind tunnel measurements (quick version).

What this script does:
    1. Loads all CSV files in  windtunnel_data/<sensor serial number>/
       The wind tunnel speed is read from the file name, e.g. "..._15ms.csv" = 15 m/s.
    2. Fits the hot-wire formula of the SVMtec manual (see function 'model') to
       voltage vs. speed. Only a, b and e are fitted; m and Uoffset come from
       calibration/daq_inputs.json and Ts is a fixed setting.
       Every 2nd sample is used for fitting ("training"), the rest for checking ("test").
    3. Prints the fitted coefficients and the error, and plots the result.

This quick version does NOT save anything. To create or update the calibration file
calibration/<sensor>.json that read_hotwire.py uses, run find_hotwire_coefficient.py.

Requirements: numpy, pandas, scipy, matplotlib
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from calibration_file import load_daq_input


# =============================================================================
# USER SETTINGS
# =============================================================================

BRIDGE_SENSOR_SN = "2025-6131"   # Sensor to calibrate (= name of the data sub-folder)
MEASUREMENT_COLUMN = "ai1"       # CSV column (= DAQ input) that contains the hot-wire voltage
FLUID_TEMPERATURE = 20           # Air temperature Tf during the wind tunnel test [°C]

# Sensor temperature Ts [°C]. It is fixed, because wind tunnel data at one air temperature
# cannot determine it (only b / (Ts - Tf) matters). 172.289596 is the value of the earlier
# 2025-6131 entry. Use the "Drahttemperatur (korr.)" of the SVMtec calibration sheet if you have it.
SENSOR_TEMPERATURE = 172.289596

# Folder with the wind tunnel files (relative to this script)
DATA_DIR = Path(__file__).parent / "windtunnel_data" / BRIDGE_SENSOR_SN


# =============================================================================
# FIT SETTINGS - normally there is no need to change these
# =============================================================================

PARAMETER_NAMES = ["a", "b", "e"]      # The fitted coefficients, in this order
INITIAL_GUESS = [-0.665, 105, 2.42]    # Starting values of the fit
LOWER_BOUNDS = [-10.0, 0.0, 1.0]       # Wide, physically sensible search range
UPPER_BOUNDS = [10.0, 1000.0, 6.0]

# Gain m and offset Uoffset of the DAQ input, from calibration/daq_inputs.json
DAQ_INPUT = load_daq_input(MEASUREMENT_COLUMN)


# =============================================================================
# FUNCTIONS
# =============================================================================

def model(u_measured, a, b, e):
    """
    Hot-wire formula of the SVMtec manual (eq. 2 and 3): measured voltage -> air speed v [m/s].

        u_bridge = u_measured / m + Uoffset
        v        = (a + b * u_bridge^2 / (Ts - Tf)) ^ e

    m and Uoffset come from DAQ_INPUT, Ts = SENSOR_TEMPERATURE, Tf = FLUID_TEMPERATURE.
    Below zero flow (a + b * ... < 0) the formula has no solution; v is then set to 0.
    """
    u_bridge = u_measured / DAQ_INPUT["m"] + DAQ_INPUT["Uoffset"]
    base = a + b * u_bridge ** 2 / (SENSOR_TEMPERATURE - FLUID_TEMPERATURE)
    return np.clip(base, 0.0, None) ** e


def find_speed_files(directory):
    """
    Find all files named like '*_<speed>ms.csv' in 'directory'.

    Returns a dictionary {file path: speed in m/s}.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"Data folder not found: {directory}")

    pattern = re.compile(r"_(\d+)ms\.csv$")
    files = {}
    for path in sorted(directory.glob("*.csv")):
        match = pattern.search(path.name)
        if match:
            files[path] = int(match.group(1))
        else:
            print(f"Skipping {path.name} (no '_<speed>ms.csv' at the end of the name)")

    if not files:
        raise FileNotFoundError(f"No files named '*_<speed>ms.csv' found in: {directory}")
    return files


def load_measurements(files, column):
    """
    Read the voltage column from every file and pair it with the speed of that file.

    Returns two 1D numpy arrays of the same length: voltages and speeds.
    """
    all_voltages = []
    all_speeds = []

    for path, speed in files.items():
        df = pd.read_csv(path)
        if column not in df.columns:
            raise ValueError(f"Column '{column}' not found in {path.name}. "
                             f"Available columns: {list(df.columns)}")

        voltages = df[column].dropna().to_numpy(dtype=float)
        print(f"Loaded {path.name}: {len(voltages)} samples at {speed} m/s")

        all_voltages.append(voltages)
        all_speeds.append(np.full(len(voltages), float(speed)))

    return np.concatenate(all_voltages), np.concatenate(all_speeds)


def check_settings(lower, upper, guess):
    """Stop with a clear message if the settings do not make sense."""
    if SENSOR_TEMPERATURE <= FLUID_TEMPERATURE:
        raise ValueError("SENSOR_TEMPERATURE must be higher than FLUID_TEMPERATURE.")

    for name, low, high, start in zip(PARAMETER_NAMES, lower, upper, guess):
        if low >= high:
            raise ValueError(f"Bounds for '{name}' are wrong: lower ({low}) >= upper ({high}).")
        if not low <= start <= high:
            raise ValueError(f"Initial guess for '{name}' ({start}) is outside the bounds "
                             f"[{low}, {high}]. Change INITIAL_GUESS, LOWER_BOUNDS or UPPER_BOUNDS.")


def warn_if_at_bounds(params, lower, upper):
    """A coefficient that ends exactly at a limit means the fit was stopped there: warn."""
    for name, value, low, high in zip(PARAMETER_NAMES, params, lower, upper):
        margin = 1e-6 * (high - low)
        if value - low < margin or high - value < margin:
            print(f"WARNING: '{name}' = {value:.6f} is at its search limit [{low}, {high}]. "
                  f"The result is probably not the best fit; widen LOWER_BOUNDS / UPPER_BOUNDS.")


def rmse(true_values, predicted_values):
    """Root mean square error."""
    return np.sqrt(np.mean((true_values - predicted_values) ** 2))


def plot_fit(u_train, v_train, u_test, v_test, params):
    """Plot the measured points and the fitted curve."""
    plt.figure(figsize=(12, 5))
    plt.scatter(u_train, v_train, s=20, label="Training data (every 2nd sample)")
    plt.scatter(u_test, v_test, s=20, label="Test data (remaining samples)")

    u_curve = np.linspace(min(u_train.min(), u_test.min()), max(u_train.max(), u_test.max()), 500)
    plt.plot(u_curve, model(u_curve, *params), linewidth=2, label="Fitted model")

    plt.xlabel("Voltage (V)")
    plt.ylabel("Speed (m/s)")
    plt.title(f"Curve fit - sensor {BRIDGE_SENSOR_SN}")
    plt.grid()
    plt.legend()
    plt.show()


# =============================================================================
# MAIN PROGRAM
# =============================================================================

def main():
    check_settings(LOWER_BOUNDS, UPPER_BOUNDS, INITIAL_GUESS)

    files = find_speed_files(DATA_DIR)
    u_all, v_all = load_measurements(files, MEASUREMENT_COLUMN)

    print(f"\nFixed values: m = {DAQ_INPUT['m']}, Uoffset = {DAQ_INPUT['Uoffset']} V "
          f"(input {MEASUREMENT_COLUMN}), Ts = {SENSOR_TEMPERATURE} °C, Tf = {FLUID_TEMPERATURE} °C")

    # Split the data: even samples for fitting, odd samples for checking
    u_train, v_train = u_all[::2], v_all[::2]
    u_test, v_test = u_all[1::2], v_all[1::2]

    params, _ = curve_fit(model, u_train, v_train, p0=INITIAL_GUESS,
                          bounds=(LOWER_BOUNDS, UPPER_BOUNDS), maxfev=200000)

    print("\nOptimized parameters:")
    for name, value in zip(PARAMETER_NAMES, params):
        print(f"{name:8s}= {value:.6f}")
    warn_if_at_bounds(params, LOWER_BOUNDS, UPPER_BOUNDS)

    print(f"\nValidation RMSE (test data) = {rmse(v_test, model(u_test, *params)):.6f} m/s")
    print("\nNothing was saved. To create the calibration file calibration/"
          f"{BRIDGE_SENSOR_SN}.json for read_hotwire.py, run find_hotwire_coefficient.py.")

    plot_fit(u_train, v_train, u_test, v_test, params)


if __name__ == "__main__":
    main()
