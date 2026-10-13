"""First Python exercise: analyse a bundled 15 m/s recording without DAQ hardware.

Run this with the project's Python environment, either from a terminal or with
VS Code's Run Python File in Terminal button. See README.md.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calibration_file import load_calibration
from hotwire_model import voltage_to_velocity

PROJECT_DIR = Path(__file__).resolve().parent
DATA_FILE = PROJECT_DIR / "calibration_data" / "2025-6104" / "20251125_101650_hotwire_measurement_windtunnel_0deg_aoa_2025-6104_15ms.csv"


def main(show_plot=True):
    data = pd.read_csv(DATA_FILE)
    calibration = load_calibration("2025-6104")
    # The bundled recording was taken at 20 C; this is a recorded input, not a fit.
    velocity, _ = voltage_to_velocity(data["ai1"].to_numpy(), calibration["coefficients"], 20.0)
    valid = velocity[np.isfinite(velocity)]
    if not len(valid):
        raise ValueError("No valid velocities could be calculated; check the calibration.")
    print(f"Read {len(data)} samples from {DATA_FILE.name}")
    print("Nominal wind tunnel speed: 15 m/s; entered air temperature: 20 C")
    print(f"Mean velocity: {np.mean(valid):.3f} m/s ({len(valid)} valid samples)")
    if show_plot:
        plt.plot(data["Runtime"], velocity, label="Calculated velocity")
        plt.axhline(15.0, color="black", linestyle="--", label="Nominal tunnel speed")
        plt.xlabel("Time (s)")
        plt.ylabel("Velocity (m/s)")
        plt.title("My first hot-wire analysis")
        plt.legend()
        plt.grid()
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-plot", action="store_true", help="print results without a plot window")
    args = parser.parse_args()
    try:
        main(show_plot=not args.no_plot)
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"ERROR: {error}") from None
