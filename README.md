# Hot-wire anemometer (SVMtec 4CTA with NI DAQ)

Python scripts to measure air velocity with a hot-wire anemometer (SVMtec 4CTA) through a National Instruments DAQ, and to calibrate the sensors with wind tunnel measurements.

| Script | What it does |
|---|---|
| `read_hotwire.py` | Records the hot-wire voltage with the NI DAQ, converts it into air velocity and saves a CSV file in `<output_folder>/` |
| `find_hotwire_coefficient.py` | Fits the calibration coefficients of a sensor from its wind tunnel measurements and saves them as `sensor_coefficients/<sensor>.json` |
| `calibration_file.py` | Helper module that reads and writes the calibration files (not run on its own) |
| `settings_file.py` | Helper module that reads and checks `user_settings.json` (not run on its own) |

All settings (sensor, test label, air temperature, ...) are in **`user_settings.json`**, see [Settings](#settings). The scripts themselves do not need to be changed.

**Hot-wire formula** (SVMtec manual `docs/Hitzdraht_doku.pdf`, section 6.5):
`v = (a + b * U_br^2 / (Ts - Tf))^e` with `U_br = U_measured / m + Uoffset`.
The fit scripts fit only `a`, `b` and `e`. `m` and `Uoffset` are the gain and offset of the DAQ input (`sensor_coefficients/daq_inputs.json`, from the factory test report `docs/PruefProtokoll_4CTA_7013_150427.pdf`), and Ts is fixed.

## Folders

| Folder | Content | In git |
|---|---|---|
| `sensor_coefficients/` | The calibration files of the sensors (see below) | yes |
| `calibration_data/<sensor>/` | The wind tunnel recordings that the calibrations are fitted from | yes |
| `docs/` | Hot-wire manual (`Hitzdraht_doku.pdf`), factory test report of the 4CTA (`PruefProtokoll_4CTA_7013_150427.pdf`) and `flowsound_v29_doku.pdf` | yes |
| `<output_folder>/` | The recordings made with `read_hotwire.py` | **no**, only on the computer that recorded them |

## Settings

All settings are in `user_settings.json`, in one section per task. Change them there. The scripts read them when they start.

**`read_hotwire`**, used by `read_hotwire.py`:

| Setting | Meaning |
|---|---|
| `sensor` | Serial number of the hot-wire sensor, e.g. `"2025-6131"`. Its calibration is `sensor_coefficients/<sensor>.json`. |
| `test_label` | Short description of the test, added to the file name. **Change it before every run.** |
| `air_temperature_C` | Air temperature Tf in °C. Measure it in the room before the test (It is not read automatically yet). |
| `measurement_time_s` | How long to record, in seconds |
| `sample_rate_Hz` | Requested samples per second. The real rate is much lower, see [Recording a measurement](#recording-a-measurement). |
| `output_folder` | Folder for the output file, relative to this folder. It is created if it does not exist. |
| `daq_device` | Name of the DAQ device (see NI MAX), e.g. `"Dev1"` |
| `daq_channels` | DAQ channels to read, e.g. `"ai1"`, `"ai1:3"` or `"ai1, ai4"` |
| `hotwire_channel_index` | Which of these channels is the hot-wire: `0` = the first one |
| `show_plot` | `true` = show a plot after the measurement |

**`calibration_fit`**, used by `find_hotwire_coefficient.py`:

| Setting | Meaning |
|---|---|
| `sensor` | Sensor to calibrate. Its wind tunnel files are in `calibration_data/<sensor>/`. |
| `voltage_column` | Column of the wind tunnel files with the hot-wire voltage (= DAQ input), e.g. `"ai1"`. Its gain and offset come from `sensor_coefficients/daq_inputs.json`. |
| `air_temperature_C` | Air temperature Tf in °C during the wind tunnel test |
| `sensor_temperatures_C` | Sensor temperature Ts in °C of every sensor. Wind tunnel data at one air temperature cannot determine it, so it is fixed. The values are those of the earlier calibration of each sensor. Use the "Drahttemperatur (korr.)" of the SVMtec calibration sheet if you have it. |
| `save_calibration` | `true` = save the result as `sensor_coefficients/<sensor>.json` (the previous file is moved to `sensor_coefficients/archive/`), `false` = only show it. |
| `calibration_note` | Remark stored in the new calibration file. Set it back to `""` afterwards, so that it does not end up in the next one. |
| `initial_guess`, `lower_bounds`, `upper_bounds` | Start values and search range of `a`, `b`, and `e`. Normally there is no need to change them. |
| `plot_error_bins` | Number of voltage bins of the "mean error" line in the plot |

The file is JSON, so:
- text goes in `"double quotes"`, numbers do not (`20.5`, with a point), and `true` / `false` are written in lower case
- settings are separated by commas, but there is no comma after the last one of a section
- in folder paths, write `/` instead of `\`
- keys that start with `_` are comments.

Before a script starts, it checks its whole section. A syntax error, a missing, misspelled or unknown setting, or a value of the wrong type stops it with a message that names the line or the setting.

## Recording a measurement

1. In `user_settings.json`, section `read_hotwire`, set `sensor`, `test_label` and `air_temperature_C`. **Change `test_label` before every run.**.
   - Wind tunnel runs for a calibration: end the label with the tunnel speed, e.g. `windtunnel_0deg_aoa_15ms`.
2. Run the script. Ctrl+C stops early. The samples recorded so far are still saved.
3. The file is saved in `output_folder` as `<date>_<time>_hotwire_measurement_<sensor>_<label>.csv`, with the columns `Timestamp`, the DAQ channel (e.g. `ai1`, the raw voltage), `Runtime`, `v` and `U_br^2/Ts-Tf`.

The samples are timed by the computer, not by the DAQ, so the real sample rate is far below `sample_rate_Hz` (34-42 Hz in all recordings so far). It is printed at the end of each run.

## Calibration files

The coefficients are not in the scripts. They are in the folder `sensor_coefficients/`:

| File | Content |
|---|---|
| `sensor_coefficients/<sensor>.json` | The active calibration of a sensor, e.g. `2025-6131.json`. `read_hotwire.py` uses it automatically for the `sensor` in its settings. |
| `sensor_coefficients/daq_inputs.json` | Gain m and offset Uoffset of the DAQ inputs ai0/ai1/ai2 (plus the PT100 and pressure conversions), with the hash of the test report they come from |
| `sensor_coefficients/archive/` | Older calibration files. They are kept so that old measurements can always be traced back.|

The sensors and their calibrations:

| Sensor | Calibration | Status |
|---|---|---|
| 2025-6131 | Fitted on 06.10.2026 from `calibration_data/2025-6131/` (25.11.2025, 0-35 m/s), test RMSE 0.17 m/s | Ready to use |
| 2025-6104 | Fitted on 06.10.2026 from `calibration_data/2025-6104/` (25.11.2025, 5-30 m/s), test RMSE 0.05 m/s | Ready to use. There is no 0 m/s point, so below 5 m/s the velocity is extrapolated |
| 2025-6121, 2025-6139 | Values from the old table in `read_hotwire.py` (probably the manufacturer's), no data | Never checked against wind tunnel data |

`read_hotwire.py` prints the notes of the calibration file before every run.

A calibration file made by `find_hotwire_coefficient.py` contains:
- `coefficients`: a, b, e, m, Uoffset and Ts.
- `fit`: how the fit was made: script (with its SHA-256 hash), fitted and fixed coefficients, air temperature, bounds, start values, training/test split.
- `source_data`: the data that was used: folder, every file with its speed, number of samples, voltage statistics and SHA-256 hash, the speed and voltage range, one hash for the whole data set (`dataset_sha256`), and the hashes of the other sources (DAQ input file, manual).
- `statistics`: the error margins:
  - `coefficient_uncertainty`: standard error and 95 % interval of `a`, `b`, and `e` from the fit, and the more realistic "leave one speed out" standard error (fit repeated without each speed)
  - `correlation` between `a`, `b`, and `e` (they are strongly correlated, so their errors largely cancel in the velocity)
  - `per_speed`: velocity bias and RMSE at every speed, and the error when that speed was not used in the fit
  - RMSE of the training and test samples.
- `software`: Python and package versions. `notes`: remarks.

To make a new calibration: move the wind tunnel files (`read_hotwire.py` saves them in `<output_folder>/`) to `calibration_data/<sensor>/`, set `sensor` and `air_temperature_C` in the `calibration_fit` section of `user_settings.json` and run `find_hotwire_coefficient.py`. Every
`..._<speed>ms.csv` file in that folder is fitted with the speed from its name, so check that each file really was recorded at that speed. For a sensor that was never calibrated before, first add its sensor temperature Ts to `sensor_temperatures_C`. The script saves `sensor_coefficients/<sensor>.json` and moves the previous file to `sensor_coefficients/archive/`. Do not edit the coefficients in a calibration file by hand.
Every file stores the formula it belongs to (`"formula": "svmtec_eq2"`). Files for another formula are refused.

## Existing data in <output_folder>/

Every file stores the raw voltage (`ai1`), so the velocity can always be calculated again with the current calibration. For example, in this folder:
```python
import pandas as pd
from calibration_file import load_calibration
from read_hotwire import voltage_to_velocity

df = pd.read_csv("<output_folder>/20251125_143650_hotwire_measurement_2025-6131_40p_100s.csv")
coeffs = load_calibration("2025-6131")["coefficients"]
v, _ = voltage_to_velocity(df["ai1"].to_numpy(), coeffs, 20)   # 20 = air temperature Tf in °C
```

## Setup on a new computer (Windows, one time)

1. Install **Python 3.10 or newer** (tested with 3.13) from <https://www.python.org/downloads/>. During the installation, tick **"Add python.exe to PATH"**.
2. Get the code (this needs Git, <https://git-scm.com/downloads>). In a terminal, in a folder with a **short path** such as `C:\code` (very long folder paths can make the installation fail because of a Windows limit):
   ```
   git clone https://github.com/TTZ-Unbemannte-Flugsysteme/hot_wire.git
   cd hot_wire
   ```
3. Open the new folder `hot_wire` in Explorer and **double-click `setup_venv.bat`**. It creates the virtual environment `.venv`, installs the packages from `requirements.txt` and checks that they can be imported. This takes a few minutes and needs internet access. At the end the window stays open and shows either "Setup finished" or a message starting with `ERROR` that says what went wrong.
   To run it from a terminal in the `hot_wire` folder instead, type `setup_venv.bat` (Command Prompt) or `.\setup_venv.bat` (PowerShell, the default terminal in VS Code).
4. Only on the measurement PC (for `read_hotwire.py`): install the NI-DAQmx driver. `setup_venv.bat` does not do this. Install it either from <https://www.ni.com> or with
   ```
   .venv\Scripts\python.exe -m nidaqmx installdriver
   ```

After a `git pull`, run `setup_venv.bat` again if `requirements.txt` has changed. It keeps the existing `.venv` and only installs or updates the packages.

Without `setup_venv.bat`, step 3 is done like this, in a terminal in the `hot_wire` folder:
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Running a script

Open a terminal in this folder and start the script with the Python from `.venv`:
```
.venv\Scripts\python.exe find_hotwire_coefficient.py
```
Or activate the environment once per terminal. After that, plain `python` works:
- Command Prompt: `.venv\Scripts\activate.bat`
- PowerShell: `.venv\Scripts\Activate.ps1` (if PowerShell says that running scripts is disabled, use the Command Prompt or the first way)

In **VS Code**: open this folder, press `Ctrl+Shift+P`, choose
"Python: Select Interpreter" and pick the one in `.venv`.

## macOS / Linux

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
The calibration scripts work on every system. `read_hotwire.py` needs the NI-DAQmx driver, which is not available for macOS.

## Adding a new package

1. Install it: `.venv\Scripts\python.exe -m pip install <package-name>`
2. Add the package name to `requirements.txt`, so that other computers get it too.
3. Commit `requirements.txt`.

## Good to know

- The `.venv` folder is **not** uploaded to GitHub (`.gitignore` excludes it). Every computer creates its own (step 3 of the setup).
- Measurement files (`*.csv`) are not stored in git, except the wind tunnel calibration data in `calibration_data/`, so the fit scripts work on every computer.
- `user_settings.json` is in git. Commit a change only if it should become the default for everyone. A new `test_label` for a single run does not need to be committed.
