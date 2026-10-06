"""
Read a hot-wire sensor through a National Instruments (NI) DAQ device.

What this script does:
    1. Reads the bridge voltage of the hot-wire for MEASUREMENT_TIME seconds.
    2. Converts every voltage sample into an air velocity (m/s) using the
       calibration file of the selected sensor: sensor_coefficients/<sensor>.json
       (made by find_hotwire_coefficient.py, see README.md).
    3. Saves everything to a CSV file in the output folder (vortifer_data/).
    4. Shows a plot of voltage and velocity over time.

How to use it:
    - Change the settings in user_settings.json (section "read_hotwire"), see README.md.
    - Run the script. Press Ctrl+C to stop early; the data recorded so far
      is still saved.

Requirements: nidaqmx, numpy, matplotlib (and the NI-DAQmx driver).
"""

import csv
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import nidaqmx
from nidaqmx.constants import TerminalConfiguration

from calibration_file import CALIBRATION_DIR, load_calibration
from settings_file import PROJECT_DIR, load_settings


# =============================================================================
# USER SETTINGS - they are in user_settings.json (section "read_hotwire"), see README.md
# =============================================================================

SETTINGS = load_settings("read_hotwire")

BRIDGE_SENSOR_SN = SETTINGS["sensor"]                       # Its calibration: sensor_coefficients/<sensor>.json
TEST_LABEL = SETTINGS["test_label"]                         # Added to the output file name
OUTPUT_DIR = PROJECT_DIR / SETTINGS["output_folder"]        # Folder for the output file
MEASUREMENT_TIME = SETTINGS["measurement_time_s"]           # How long to record [s]
SAMPLE_RATE = SETTINGS["sample_rate_Hz"]                    # Requested samples per second (see record_samples)
FLUID_TEMPERATURE = SETTINGS["air_temperature_C"]           # Air temperature Tf [°C], entered by hand
DEVICE = SETTINGS["daq_device"]                             # Name of the DAQ device (see NI MAX)
CHANNELS = SETTINGS["daq_channels"]                         # Channels to read, e.g. "ai1" or "ai1:3"
HOTWIRE_CHANNEL_INDEX = SETTINGS["hotwire_channel_index"]   # 0 = the first channel in CHANNELS
SHOW_PLOT = SETTINGS["show_plot"]                           # Show a plot after the measurement?


# =============================================================================
# FUNCTIONS
# =============================================================================

def voltage_to_temp(voltage, current=0.002, r0=100.0):
    """
    Convert the voltage of a PT100 temperature sensor into a temperature [°C].

    NOTE: Currently NOT used. Reading the temperature this way gave wrong
    values, so FLUID_TEMPERATURE is entered by hand instead.
    """
    a = 3.9083e-3   # Callendar-Van Dusen coefficient A of a PT100
    b = -5.775e-7   # Callendar-Van Dusen coefficient B of a PT100
    resistance = voltage / current
    temperature = (-a + np.sqrt(a**2 - 4*b*(1 - resistance/r0))) / (2*b)
    return temperature


def get_calibration(sensor_sn):
    """
    Read the calibration file of the sensor (sensor_coefficients/<sensor>.json) and print where it comes from.

    Returns the content of the file; the coefficients are in calibration["coefficients"].
    """
    calibration = load_calibration(sensor_sn)
    source = calibration.get("source_data") or {}
    statistics = calibration.get("statistics") or {}

    print(f"Calibration file: {CALIBRATION_DIR.name}/{sensor_sn}.json (created {calibration.get('created')})")
    if source.get("dataset_sha256"):
        low, high = source["speed_range_m_per_s"]
        print(f"  fitted from {source['number_of_files']} files in {source['folder']}, "
              f"speeds {low:g}-{high:g} m/s, data hash {source['dataset_sha256'][:12]}")
    else:
        print(f"  {source.get('description', 'no description of the source data')}")
    if statistics.get("rmse_test_m_per_s") is not None:
        print(f"  fit error (RMSE): {statistics['rmse_test_m_per_s']:.3f} m/s")
    for note in calibration.get("notes", []):
        print(f"  NOTE: {note}")
    return calibration


def warn_if_outside_calibration(velocity, calibration):
    """Warn if velocities are above the highest calibrated speed (those values are extrapolated)."""
    speed_range = (calibration.get("source_data") or {}).get("speed_range_m_per_s")
    if not speed_range:
        return
    above = np.count_nonzero(velocity > speed_range[1])
    if above > 0:
        print(f"WARNING: {above} of {len(velocity)} samples ({100 * above / len(velocity):.0f} %) are above "
              f"the highest calibrated speed ({speed_range[1]:g} m/s); these values are extrapolated.")


def expand_channels(channel_text):
    """
    Turn a channel string into a list of channel names.

    Examples:
        "ai1:3"     -> ["ai1", "ai2", "ai3"]
        "ai1, ai4"  -> ["ai1", "ai4"]
        "ai1"       -> ["ai1"]
    """
    channel_text = channel_text.strip()

    if ":" in channel_text and "," not in channel_text:
        prefix = "".join(c for c in channel_text if c.isalpha())   # e.g. "ai"
        numbers = channel_text[len(prefix):]                         # e.g. "1:3"
        first, last = [int(x) for x in numbers.split(":", 1)]
        return [f"{prefix}{i}" for i in range(first, last + 1)]

    return [name.strip() for name in channel_text.split(",") if name.strip()]


def make_output_path(output_dir, sensor_sn, test_label):
    """
    Build a path like '<output_dir>/20251125_174446_hotwire_measurement_2025-6131_40p_100s_cw.csv'
    and create 'output_dir' if needed.
    If the file already exists, '_1', '_2', ... is added so nothing is overwritten.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp}_hotwire_measurement_{sensor_sn}_{test_label}"

    out_path = output_dir / f"{base_name}.csv"
    counter = 1
    while out_path.exists():
        out_path = output_dir / f"{base_name}_{counter}.csv"
        counter += 1
    return out_path


def record_samples(device, channels, measurement_time, sample_rate):
    """
    Read voltages from the DAQ for 'measurement_time' seconds.

    NOTE: The timing is done by the computer (time.sleep), not by the DAQ
    hardware. The real sample rate is therefore LOWER than 'sample_rate'.
    The achieved rate is printed at the end.

    Returns:
        timestamps: list of date/time strings, one per sample
        voltages:   2D numpy array, one row per sample, one column per channel
        runtimes:   1D numpy array, seconds since the start of the measurement
    """
    pause_between_samples = 1.0 / sample_rate

    timestamps = []
    voltages = []
    runtimes = []

    with nidaqmx.Task() as task:
        task.ai_channels.add_ai_voltage_chan(
            f"{device}/{channels}",
            terminal_config=TerminalConfiguration.RSE,
            min_val=-10.0,
            max_val=10.0,
        )

        print(f"Recording {device}/{channels} for {measurement_time} s ... (Ctrl+C to stop early)")
        start = time.time()

        try:
            while time.time() - start < measurement_time:
                value = task.read()          # float (1 channel) or list (several channels)
                if isinstance(value, float):
                    value = [value]

                now = time.time()
                timestamps.append(datetime.fromtimestamp(now).strftime("%Y:%m:%d:%H:%M:%S.%f")[:-2])
                voltages.append(value)
                runtimes.append(now - start)

                time.sleep(pause_between_samples)
        except KeyboardInterrupt:
            print("\nMeasurement stopped by user. Saving the data recorded so far.")

    if len(voltages) == 0:
        raise RuntimeError("No samples were recorded.")

    runtimes = np.array(runtimes)
    if runtimes[-1] > 0:
        print(f"Recorded {len(runtimes)} samples in {runtimes[-1]:.1f} s "
              f"(achieved rate = {len(runtimes) / runtimes[-1]:.0f} Hz)")

    return timestamps, np.array(voltages), runtimes


def voltage_to_velocity(u_measured, coeffs, fluid_temperature):
    """
    Convert the measured hot-wire voltage into air velocity [m/s].

        u_bridge_squared = (u_measured / m + u_offset)^2
        v                = (a + b * u_bridge_squared / (Ts - Tf)) ^ e

    with Ts = sensor temperature (coefficient "Ts") and Tf = fluid temperature.

    Returns:
        v:     velocity [m/s]  (NaN where the formula has no real solution)
        ratio: u_bridge_squared / (Ts - Tf), saved in the CSV column "U_br^2/Ts-Tf"
    """
    a = coeffs["a"]
    b = coeffs["b"]
    e = coeffs["e"]
    m = coeffs["m"]
    u_offset = coeffs["Uoffset"]
    sensor_temperature = coeffs["Ts"]

    if sensor_temperature == fluid_temperature:
        raise ValueError("Sensor temperature Ts equals the fluid temperature: division by zero.")

    u_bridge_squared = ((u_measured / m) + u_offset) ** 2
    ratio = u_bridge_squared / (sensor_temperature - fluid_temperature)

    # A negative number to a non-integer power gives NaN. Hide numpy's warning
    # and report the number of NaN values ourselves instead.
    with np.errstate(invalid="ignore"):
        v = (a + b * ratio) ** e

    n_invalid = np.count_nonzero(np.isnan(v))
    if n_invalid > 0:
        print(f"WARNING: {n_invalid} of {len(v)} samples gave no valid velocity (NaN). "
              f"This is normal at (almost) zero air speed.")

    return v, ratio


def save_csv(out_path, channel_names, timestamps, voltages, runtimes, velocity, ratio):
    """
    Write all data to a CSV file.
    The column names must match older measurement files, so do not rename them.
    """
    header = ["Timestamp"] + channel_names + ["Runtime", "v", "U_br^2/Ts-Tf"]

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(len(timestamps)):
            row = [timestamps[i]] + list(voltages[i]) + [runtimes[i], velocity[i], ratio[i]]
            writer.writerow(row)

    print(f"Saved {len(timestamps)} samples for {len(channel_names)} channel(s) to {out_path}")


def plot_measurement(channel_names, voltages, runtimes, velocity):
    """Plot the raw voltage of every channel and the computed velocity over time."""
    plt.figure()
    for i, name in enumerate(channel_names):
        plt.plot(runtimes, voltages[:, i], label=f"{name} (V)")
    plt.plot(runtimes, velocity, label="Velocity (m/s)")

    plt.xlabel("Time (s)")
    plt.ylabel("Voltage (V) / Velocity (m/s)")
    plt.title(f"{DEVICE} - {len(runtimes)} samples")
    plt.legend()
    plt.grid()
    plt.tight_layout()
    plt.show()


# =============================================================================
# MAIN PROGRAM
# =============================================================================

def main():
    calibration = get_calibration(BRIDGE_SENSOR_SN)
    coeffs = calibration["coefficients"]
    channel_names = expand_channels(CHANNELS)

    if not 0 <= HOTWIRE_CHANNEL_INDEX < len(channel_names):
        raise ValueError(f'"hotwire_channel_index" in user_settings.json is {HOTWIRE_CHANNEL_INDEX}, '
                         f"but only {len(channel_names)} channel(s) are read: {channel_names}")

    print(f"Sensor: {BRIDGE_SENSOR_SN}")
    print(f"Fluid temperature Tf = {FLUID_TEMPERATURE} °C")

    out_path = make_output_path(OUTPUT_DIR, BRIDGE_SENSOR_SN, TEST_LABEL)

    timestamps, voltages, runtimes = record_samples(DEVICE, CHANNELS, MEASUREMENT_TIME, SAMPLE_RATE)

    hotwire_voltage = voltages[:, HOTWIRE_CHANNEL_INDEX]
    velocity, ratio = voltage_to_velocity(hotwire_voltage, coeffs, FLUID_TEMPERATURE)
    warn_if_outside_calibration(velocity, calibration)

    save_csv(out_path, channel_names, timestamps, voltages, runtimes, velocity, ratio)

    if SHOW_PLOT:
        plot_measurement(channel_names, voltages, runtimes, velocity)


if __name__ == "__main__":
    main()
