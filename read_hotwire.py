"""
Read a hot-wire sensor through a National Instruments (NI) DAQ device.

What this script does:
    1. Reads the bridge voltage of the hot-wire for MEASUREMENT_TIME seconds.
    2. Converts every voltage sample into an air velocity (m/s) using the
       calibration file of the selected sensor: sensor_coefficients/<sensor>.json
       (made by find_hotwire_coefficient.py, see README.md).
    3. Writes each sample to CSV and saves settings/calibration in a metadata JSON file.
    4. Shows a plot of voltage and velocity over time.

How to use it:
    - Change user_settings.local.json (section "read_hotwire"), see README.md.
    - Run the script. Press Ctrl+C to stop early. The data recorded so far
      is still saved.

Requirements: nidaqmx, numpy, matplotlib (and the NI-DAQmx driver).
"""

import csv
import math
import platform
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from calibration_file import (CALIBRATION_DIR, HASH_METHOD, calibration_path, file_sha256,
                              load_calibration, load_daq_input, write_json)
from hotwire_model import validate_conversion, voltage_to_velocity as convert_voltage
from settings_file import PROJECT_DIR, expand_channels, load_settings, settings_path


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

    Returns the content of the file. The coefficients are in calibration["coefficients"].
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
    """Warn about extrapolation below or above the calibrated speed range."""
    speed_range = (calibration.get("source_data") or {}).get("speed_range_m_per_s")
    if not speed_range:
        return
    for direction, count, limit in (
            ("below", np.count_nonzero(velocity < speed_range[0]), speed_range[0]),
            ("above", np.count_nonzero(velocity > speed_range[1]), speed_range[1])):
        if count:
            print(f"WARNING: {count} of {np.size(velocity)} samples are {direction} the calibrated "
                  f"speed limit ({limit:g} m/s). These values are extrapolated.")


def check_calibration_channel(calibration, channel):
    """Require the same DAQ input and gain/offset that were used for fitting."""
    fitted_channel = (calibration.get("source_data") or {}).get("voltage_column")
    if fitted_channel != channel:
        raise ValueError(f"This calibration was fitted for {fitted_channel!r}, but the selected hot-wire "
                         f"channel is {channel!r}. Use the calibrated channel or fit a calibration for the new input.")
    daq_input = load_daq_input(channel)
    for name in ("m", "Uoffset"):
        if not math.isclose(calibration["coefficients"][name], daq_input[name], rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(f"The {channel} {name} has changed since calibration. Check daq_inputs.json and refit before recording.")


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
    while out_path.exists() or out_path.with_suffix(".metadata.json").exists():
        out_path = output_dir / f"{base_name}_{counter}.csv"
        counter += 1
    return out_path


def record_samples(device, channels, measurement_time, sample_rate, on_sample=None):
    """
    Read voltages from the DAQ for 'measurement_time' seconds.

    NOTE: The timing is done by the computer (time.sleep), not by the DAQ
    hardware. The real sample rate is therefore LOWER than 'sample_rate'.
    The achieved rate is printed at the end.

    Returns:
        timestamps: list of date/time strings, one per sample
        voltages:   2D numpy array, one row per sample, one column per channel
        runtimes:   1D numpy array, seconds since the start of the measurement
        outcome:    status (complete/stopped/failed), elapsed time and any DAQ error
    on_sample(timestamp, voltages, runtime) writes each sample while recording.
    """
    try:
        import nidaqmx
        from nidaqmx.constants import TerminalConfiguration
    except ImportError:
        raise RuntimeError("Recording needs nidaqmx: install requirements-daq.txt (see README.md).") from None
    if not math.isfinite(sample_rate) or sample_rate <= 0 or not math.isfinite(measurement_time) or measurement_time <= 0:
        raise ValueError("Measurement duration and sample rate must be finite numbers greater than zero.")
    channel_names = expand_channels(channels)
    physical_channels = ",".join(f"{device}/{name}" for name in channel_names)
    pause_between_samples = 1.0 / sample_rate

    timestamps = []
    voltages = []
    runtimes = []

    outcome = {"status": "complete"}
    start = time.perf_counter()
    try:
        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan(
                physical_channels, terminal_config=TerminalConfiguration.RSE,
                min_val=-10.0, max_val=10.0)
            print(f"Recording {physical_channels} for {measurement_time} s ... (Ctrl+C to stop early)")
            start = time.perf_counter()
            while time.perf_counter() - start < measurement_time:
                value = np.atleast_1d(np.asarray(task.read(), dtype=float)).tolist()
                if len(value) != len(channel_names):
                    raise RuntimeError(f"DAQ returned {len(value)} values for {len(channel_names)} channels.")
                runtime = time.perf_counter() - start
                timestamp = datetime.now().strftime("%Y:%m:%d:%H:%M:%S.%f")[:-2]
                if on_sample is not None:
                    on_sample(timestamp, value, runtime)
                timestamps.append(timestamp)
                voltages.append(value)
                runtimes.append(runtime)
                time.sleep(pause_between_samples)
    except KeyboardInterrupt:
        outcome["status"] = "stopped"
        print("\nMeasurement stopped by user. Samples already written to CSV are kept.")
    except nidaqmx.errors.Error as error:
        outcome.update(status="failed", error=str(error))
        print(f"\nDAQ error: {error}. Samples already written to CSV are kept.")
    outcome["elapsed_time_s"] = time.perf_counter() - start

    if len(voltages) == 0:
        raise RuntimeError("No samples were recorded. " + outcome.get("error", "Check the driver and device in NI MAX."))

    runtimes = np.array(runtimes)
    achieved_rate = (len(runtimes) - 1) / (runtimes[-1] - runtimes[0]) if len(runtimes) > 1 and runtimes[-1] > runtimes[0] else None
    outcome["achieved_sample_rate_Hz"] = achieved_rate
    if achieved_rate is not None:
        print(f"Recorded {len(runtimes)} samples in {runtimes[-1]:.1f} s "
              f"(achieved rate = {achieved_rate:.0f} Hz)")

    return timestamps, np.array(voltages), runtimes, outcome


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
    v, ratio = convert_voltage(u_measured, coeffs, fluid_temperature)
    n_invalid = np.count_nonzero(~np.isfinite(v))
    if n_invalid > 0:
        print(f"WARNING: {n_invalid} of {np.size(v)} samples gave no valid velocity (NaN). "
              "Check raw voltage and the calibrated range; the formula can be invalid near zero flow.")

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


def plot_measurement(channel_names, voltages, runtimes, velocity, device):
    """Plot the raw voltage of every channel and the computed velocity over time."""
    plt.figure()
    for i, name in enumerate(channel_names):
        plt.plot(runtimes, voltages[:, i], label=f"{name} (V)")
    plt.plot(runtimes, velocity, label="Velocity (m/s)")

    plt.xlabel("Time (s)")
    plt.ylabel("Voltage (V) / Velocity (m/s)")
    plt.title(f"{device}, {len(runtimes)} samples")
    plt.legend()
    plt.grid()
    plt.tight_layout()
    plt.show()


# =============================================================================
# MAIN PROGRAM
# =============================================================================

def main():
    settings = load_settings("read_hotwire")
    calibration = get_calibration(settings["sensor"])
    coeffs = calibration["coefficients"]
    channel_names = expand_channels(settings["daq_channels"])
    hotwire_index = settings["hotwire_channel_index"]
    check_calibration_channel(calibration, channel_names[hotwire_index])
    validate_conversion(coeffs, settings["air_temperature_C"])
    print(f"Settings: {settings_path().name}")
    print(f"Sensor: {settings['sensor']}; air temperature Tf = {settings['air_temperature_C']} C")
    print("Timing is controlled by the computer; the achieved rate can be much lower than requested.")
    out_path = make_output_path(PROJECT_DIR / settings["output_folder"], settings["sensor"], settings["test_label"])
    metadata_path = out_path.with_suffix(".metadata.json")
    metadata = {
        "format_version": 1, "created": datetime.now().astimezone().isoformat(),
        "csv_file": out_path.name, "settings_file": settings_path().name,
        "settings": settings, "settings_sha256": file_sha256(settings_path()),
        "calibration_file": f"sensor_coefficients/{settings['sensor']}.json",
        "calibration_sha256": file_sha256(calibration_path(settings["sensor"])),
        "calibration": calibration, "hotwire_channel": channel_names[hotwire_index],
        "hash_method": HASH_METHOD, "script_sha256": file_sha256(__file__),
        "model_script_sha256": file_sha256(Path(__file__).resolve().parent / "hotwire_model.py"),
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "status": "recording", "samples": 0,
    }
    write_json(metadata_path, metadata)
    try:
        with open(out_path, "x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp"] + channel_names + ["Runtime", "v", "U_br^2/Ts-Tf"])
            f.flush()

            def write_sample(timestamp, values, runtime):
                v, ratio = convert_voltage(values[hotwire_index], coeffs, settings["air_temperature_C"])
                writer.writerow([timestamp] + values + [runtime, float(v), float(ratio)])
                metadata["samples"] += 1
                f.flush()

            timestamps, voltages, runtimes, outcome = record_samples(
                settings["daq_device"], settings["daq_channels"], settings["measurement_time_s"],
                settings["sample_rate_Hz"], on_sample=write_sample)
        metadata.update(outcome)
    except (Exception, KeyboardInterrupt) as error:
        metadata.update(status="failed", error=str(error) or "Interrupted before recording finished.")
        if out_path.exists():
            metadata["csv_sha256"] = file_sha256(out_path)
        write_json(metadata_path, metadata)
        raise
    metadata["csv_sha256"] = file_sha256(out_path)
    write_json(metadata_path, metadata)
    print(f"Saved {metadata['samples']} samples to {out_path}")
    print(f"Saved settings and calibration to {metadata_path}")
    if outcome["status"] == "failed":
        raise RuntimeError("Acquisition failed. The partial CSV and metadata were saved; see the DAQ error above.")
    velocity, _ = voltage_to_velocity(voltages[:, hotwire_index], coeffs, settings["air_temperature_C"])
    warn_if_outside_calibration(velocity, calibration)
    if settings["show_plot"]:
        plot_measurement(channel_names, voltages, runtimes, velocity, settings["daq_device"])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"ERROR: {error}") from None
