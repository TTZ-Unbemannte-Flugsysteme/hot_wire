# Experiment: propeller characterization

Python scripts for the propeller test stand and the hot-wire anemometer (SVMtec 4CTA with NI DAQ).

| Script | What it does |
|---|---|
| `read_hotwire.py` | Records the hot-wire voltage with the NI DAQ, converts it into air velocity and saves a CSV file in `vortifer_data/` |
| `find_hotwire_coefficient.py` | Fits the hot-wire calibration coefficients from wind tunnel measurements and saves them as `calibration/<sensor>.json` |
| `optimization.py` | Quick version of the same fit (prints the result, saves nothing) |
| `recompute_velocity.py` | Recalculates the velocity in existing measurement files in `vortifer_data/` with the current calibration (writes copies to `recomputed_velocity/`) |
| `experimental_propeller_characterization.py` | Calculates the thrust and lift coefficients C_T and C_L from test stand data |
| `calibration_file.py` | Helper module that reads and writes the calibration files (not run on its own) |

The settings of each script (sensor, file names, ...) are in the **USER SETTINGS** block at the top of the file.

**Hot-wire formula** (SVMtec manual `Hitzdraht_doku.pdf`, section 6.5):
`v = (a + b * U_br^2 / (Ts - Tf))^e` with `U_br = U_measured / m + Uoffset`.
The fit scripts fit only a, b and e; m and Uoffset are the gain and offset of the DAQ input
(`calibration/daq_inputs.json`, from the factory test report `PruefProtokoll_4CTA_7013_150427.pdf`),
and Ts is fixed.

## Calibration files

The coefficients are not in the scripts; they are in the folder `calibration/`:

| File | Content |
|---|---|
| `calibration/<sensor>.json` | The active calibration of a sensor, e.g. `2025-6131.json`. `read_hotwire.py` uses it automatically for `BRIDGE_SENSOR_SN`. |
| `calibration/daq_inputs.json` | Gain m and offset Uoffset of the DAQ inputs ai0/ai1/ai2 (plus the PT100 and pressure conversions), with the hash of the test report they come from |
| `calibration/archive/` | Older calibration files. They are kept so that old measurements can always be traced back. |

A calibration file made by `find_hotwire_coefficient.py` contains:
- `coefficients`: a, b, e, m, Uoffset and Ts.
- `fit`: how the fit was made: script (with its SHA-256 hash), fitted and fixed coefficients, air
  temperature, bounds, start values, training/test split.
- `source_data`: the data that was used: folder, every file with its speed, number of samples,
  voltage statistics and SHA-256 hash, the speed and voltage range, one hash for the whole
  data set (`dataset_sha256`), and the hashes of the other sources (DAQ input file, manual).
- `statistics`: the error margins:
  - `coefficient_uncertainty`: standard error and 95 % interval of a, b and e from the fit, and
    the more realistic "leave one speed out" standard error (fit repeated without each speed);
  - `correlation` between a, b and e (they are strongly correlated, so their errors largely
    cancel in the velocity);
  - `per_speed`: velocity bias and RMSE at every speed, and the error when that speed was not
    used in the fit;
  - RMSE of the training and test samples.
- `software`: Python and package versions; `notes`: remarks.

To make a new calibration: move the wind tunnel files (`read_hotwire.py` saves them in
`vortifer_data/`) to `windtunnel_data/<sensor>/` and run `find_hotwire_coefficient.py`. Every
`..._<speed>ms.csv` file in that folder is fitted with the speed from its name, so check that each
file really was recorded at that speed. The script saves `calibration/<sensor>.json` and moves the
previous file to `calibration/archive/`. Do not edit the coefficients in a calibration file by hand.
Every file stores the formula it belongs to (`"formula": "svmtec_eq2"`); files for another formula
are refused.

**Note on 2025-6131 data of 25.11.2025** (in `vortifer_data/`): these files were recorded with
coefficients that were fitted with a different formula; their velocity column `v` is 25-38 % too
low. Use the corrected copies in `recomputed_velocity/` (made with `recompute_velocity.py`).
Three files of that afternoon were saved with a leftover wind tunnel label
(`..._windtunnel_0deg_aoa_2025-6131_35ms.csv`), although none of them is 35 m/s data. They were
renamed to `20251125_141439_..._noflow.csv`, `20251125_141805_..._lowflow.csv` and
`20251125_143023_..._unknown_throttle.csv` (a propeller run whose throttle is not known).

## Setup on a new computer (Windows, one time)

1. Install **Python 3.10 or newer** (tested with 3.13) from <https://www.python.org/downloads/>.
   During the installation, tick **"Add python.exe to PATH"**.
2. Get the code. In a terminal, in a folder with a **short path** such as `C:\code`
   (very long folder paths can make the installation fail because of a Windows limit):
   ```
   git clone https://github.com/TTZ-Unbemannte-Flugsysteme/Vortifer_research.git
   ```
3. Open the folder `Vortifer_research\experiment_propeller_characterization` and
   **double-click `setup_venv.bat`**. It creates the sub-folder `.venv` with all
   required packages. This takes a few minutes and needs internet access.
4. Only on the measurement PC (for `read_hotwire.py`): install the NI-DAQmx driver,
   either from <https://www.ni.com> or with
   ```
   .venv\Scripts\python.exe -m nidaqmx installdriver
   ```

After a `git pull`, run `setup_venv.bat` again if `requirements.txt` has changed.

## Running a script

Open a terminal in this folder and start the script with the Python from `.venv`:
```
.venv\Scripts\python.exe find_hotwire_coefficient.py
```
Or activate the environment once per terminal; after that, plain `python` works:
- Command Prompt: `.venv\Scripts\activate.bat`
- PowerShell: `.venv\Scripts\Activate.ps1`
  (if PowerShell says that running scripts is disabled, use the Command Prompt or the first way)

In **VS Code**: open this folder, press `Ctrl+Shift+P`, choose
"Python: Select Interpreter" and pick the one in `.venv`.

## macOS / Linux

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
The analysis scripts work on every system. `read_hotwire.py` needs the NI-DAQmx driver,
which is not available for macOS.

## Adding a new package

1. Install it: `.venv\Scripts\python.exe -m pip install <package-name>`
2. Add the package name to `requirements.txt`, so that other computers get it too.
3. Commit `requirements.txt`.

## Good to know

- The `.venv` folder is **not** uploaded to GitHub (the repository's `.gitignore` excludes it).
  Every computer creates its own with `setup_venv.bat`.
- `experimental_propeller_characterization.py` reads `configs/vortifer_config.py` from the
  repository root, so always clone the whole repository.
- Measurement files (`*.csv`) are not stored in git (see `.gitignore`), except the wind tunnel
  calibration data in `windtunnel_data/`, so the fit scripts work on every computer. Throttle runs
  (every file with `_<number>p_` in its name, e.g. `..._40p_100s.csv`) are never stored in git,
  in any folder. To use `data/`, `vortifer_data/` or `recomputed_velocity/` on another computer,
  copy the folder there.
