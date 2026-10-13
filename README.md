# Hot-wire anemometer (SVMtec 4CTA with NI DAQ)

Python scripts for measuring air velocity and fitting hot-wire sensor calibrations from wind tunnel data.

**Start with the supplied data.** You can run the analysis example and calibration exercise on your own computer without a sensor, NI hardware or NI drivers. Recording new measurements requires the laboratory equipment and its driver.

## Contents

- [Scripts at a glance](#scripts-at-a-glance)
- [Installation and setup (all operating systems)](#installation-and-setup-all-operating-systems)
  - [Step 1. Install Python and an optional editor](#step-1-install-python-and-an-optional-editor)
  - [Step 2. Download and extract the project](#step-2-download-and-extract-the-project)
  - [Step 3. Create `.venv` and install project packages](#step-3-create-venv-and-install-project-packages)
  - [Step 4. Activate `.venv` when opening a new terminal](#step-4-activate-venv-when-opening-a-new-terminal)
  - [Step 5. Check the setup and run the supplied example](#step-5-check-the-setup-and-run-the-supplied-example)
  - [Step 6. Install the NI system driver (laboratory PC only)](#step-6-install-the-ni-system-driver-laboratory-pc-only)
- [Run a Python script](#run-a-python-script)
- [Check your setup](#check-your-setup)
- [Your settings](#your-settings)
- [Try calibration without changing the active file](#try-calibration-without-changing-the-active-file)
- [Record a measurement (laboratory PC)](#record-a-measurement-laboratory-pc)
- [Read and back up your results](#read-and-back-up-your-results)
- [Fit and save a new calibration](#fit-and-save-a-new-calibration)
- [Calibration reference](#calibration-reference)
- [Troubleshooting](#troubleshooting)
- [Update or recreate the environment](#update-or-recreate-the-environment)
- [Developer checks](#developer-checks)
- [License](#license)

## Scripts at a glance

| Script | Purpose |
|---|---|
| `analyse_example.py` | First exercise: plot a supplied 15 m/s recording and calculate its mean velocity. Does not write files. |
| `find_hotwire_coefficient.py` | Fit calibration coefficients from wind tunnel recordings. Saving is disabled by default. |
| `read_hotwire.py` | Record voltage with the NI DAQ and write a CSV with a settings/calibration snapshot. |
| `check_setup.py` | Check packages, settings, input data and file access; optionally check NI hardware. |
| `install_ni_driver.py` | Launch the separate NI system-driver installer on the measurement PC, requesting administrator access when needed. |
| `hotwire_model.py`, `calibration_file.py`, `settings_file.py` | Helper modules imported by the scripts above; do not run them on their own. |

## Installation and setup (all operating systems)

Follow the numbered steps below, choosing the instructions for your operating system within each step. **For the supplied analysis exercises, finish at Step 5. For recording on a laboratory PC, also complete Step 6.**

New to terminals? [VS Code's beginner terminal guide](https://code.visualstudio.com/docs/terminal/getting-started) explains how to open one and run commands, with screenshots. From Step 3 onwards, commands assume your terminal is in the downloaded project folder containing `README.md`.

A **script** is a `.py` file containing Python instructions. **Packages** provide tools such as plotting and curve fitting. **`.venv`** is a private Python environment for this project. Activation makes `python` use that environment and its installed packages.

### Step 1. Install Python and an optional editor

Python **3.13** is recommended, as it was used for the supplied calibrations. The setup helper accepts Python 3.10 or newer, prefers 3.13 when available, and checks that the selected interpreter works. If a suitable version is already installed, keep it and continue.

**For Windows:** get the [Python Install Manager](https://www.python.org/downloads/) and follow the [official Windows installation instructions](https://docs.python.org/3/using/windows.html). With the manager installed, run:

```powershell
py install 3.13
py -3.13 --version
```

The second command should print `Python 3.13.x`.

**For Linux / WSL:** check the existing version in your Linux terminal:

```sh
python3 --version
```

On Ubuntu, including Ubuntu in WSL, install the full Python runtime and virtual-environment support if needed:

```sh
sudo apt update
sudo apt install python3-full
```

See [Ubuntu's Python setup guide](https://ubuntu.com/developers/docs/howto/python-setup/) for details. For other distributions, use their package manager and the [Python Linux installation guide](https://docs.python.org/3/using/unix.html). Some distributions package virtual-environment support separately as `python3-venv`. These system prerequisites may need administrator access; the project package setup in Step 3 runs as your normal user.

**For macOS:** download the Python 3.13 macOS installer from [python.org](https://www.python.org/downloads/macos/) and follow the [official macOS installation instructions](https://docs.python.org/3/using/mac.html), including the **Install Certificates.command** step. Then check:

```sh
python3 --version
```

**Optional editor, all operating systems:** if you want to use VS Code's Run button, install [Visual Studio Code](https://code.visualstudio.com/) and its [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python). For WSL, install VS Code on Windows and use its WSL extension to open the Linux project; follow [VS Code's WSL setup guide](https://code.visualstudio.com/docs/remote/wsl). The [running instructions below](#run-a-python-script) explain interpreter selection and the Run button.

### Step 2. Download and extract the project

**All operating systems:** on the [GitHub repository](https://github.com/TTZ-Unbemannte-Flugsysteme/hot_wire), choose **Code > Download ZIP**, then extract the ZIP. Work in the extracted folder containing `README.md`.

**For Windows:** use **Extract All** in Windows Explorer. A short path such as `C:\code\hot_wire` avoids Windows path-length problems.

**For Linux / WSL / macOS:** use your file manager's extraction option and keep the project in a writable folder. In WSL, use your Linux home folder, for example `~/python_playground/hot_wire`. Keep separate Windows and WSL checkouts and environments.

**Git alternative, all operating systems:** if you already use Git, install [Git](https://git-scm.com/downloads) if needed, then run:

```sh
git clone https://github.com/TTZ-Unbemannte-Flugsysteme/hot_wire.git
cd hot_wire
```

### Step 3. Create `.venv` and install project packages

The setup helper creates `.venv`, installs packages, creates `user_settings.local.json` if missing, runs the setup checks, and activates the environment. It needs internet access and may take a few minutes. Choose the analysis command for your own computer or the recording command for the laboratory PC.

**For Windows:** double-click `setup_venv.bat` for analysis, or run the appropriate command from the project folder:

| Purpose | Command |
|---|---|
| Analysis and calibration exercises | `.\setup_venv.bat` |
| Recording on the laboratory PC | `.\setup_venv.bat daq` |

The helper opens a **Command Prompt with `.venv` activated**. Keep that prompt open for the next steps. If setup fails, the error window stays open; follow the reported fix and rerun setup.

**For Linux / WSL / macOS:** use Bash or zsh and **source** the appropriate helper:

| Purpose | Command |
|---|---|
| Analysis and calibration exercises | `source ./setup_venv.sh` |
| Recording on a supported native Linux PC | `source ./setup_venv.sh daq` |

Sourcing runs setup in your current terminal and keeps `.venv` activated. It also avoids the `Permission denied` error from trying to execute `./setup_venv.sh` directly; sourcing does not require executable permission. Run this step **without `sudo`**. WSL and macOS are used here for analysis; this project's hardware workflow requires Windows or supported native Linux.

**All operating systems:** success includes `All required checks passed` and `Setup finished`. Review any `[WARN]` messages using [Check your setup](#check-your-setup). Setup preserves existing local settings when rerun. With the `daq` option, it installs the DAQ Python package; the separate system driver is installed in Step 6.

### Step 4. Activate `.venv` when opening a new terminal

Setup already activates the environment. Use this step for later sessions, from the project folder. Activation applies to the current terminal only; closing it ends activation.

**For Windows:** double-click `activate_venv.bat`, or run:

```powershell
.\activate_venv.bat
```

This opens an activated Command Prompt, including when launched from PowerShell. Run Python commands in that prompt; type `exit` to close it and return to your original terminal. A batch file cannot activate its parent PowerShell session.

**For Linux / WSL / macOS:** run:

```sh
source ./activate_venv.sh
```

The direct activation command is also available:

```sh
source .venv/bin/activate
```

Use `deactivate` to leave the environment when finished.

**All operating systems:** look for **`(.venv)`** at the prompt. These activation helpers reuse the existing environment without reinstalling packages. If it is missing, return to Step 3.

### Step 5. Check the setup and run the supplied example

**All operating systems:** in the activated terminal, run:

```sh
python check_setup.py
```

The check should finish with `0 error(s)` and `All required checks passed`. Fix any `[ERROR]` messages before continuing. Its `Python:` line should point to this project's `.venv`. If you run the check with system Python, such as `/usr/bin/python3` before activation on Linux/WSL, it stops and points you back to Step 4. Older or missing packages in system Python do not mean the project environment needs reinstalling.

Then run the example:

```sh
python analyse_example.py
```

The example should print `Read 341 samples` and a mean velocity of about **14.976 m/s**, then show a plot. Close the plot window to return to the terminal. It uses supplied data and does not save or replace anything. Add `--no-plot` to the example command if you want just the printed results.

**Analysis setup is complete.** Use [Run a Python script](#run-a-python-script) and [Try calibration](#try-calibration-without-changing-the-active-file) for the exercises. Continue below only when setting up a measurement PC.

### Step 6. Install the NI system driver (laboratory PC only)

First use the **recording** command in Step 3 so `nidaqmx` is installed in `.venv`. The Python package and system driver are separate installations. Check your hardware, operating system and driver combination against [NI's compatibility information](https://www.ni.com/en/support/documentation/compatibility/21/ni-hardware-and-operating-system-compatibility.html).

**For Windows:** in the activated Command Prompt, run:

```sh
python install_ni_driver.py
```

Follow NI's installer and its administrator prompt. A separate Windows checkout and `.venv` are needed when moving from WSL to Windows for recording.

**For native Linux:** in the activated Bash/zsh terminal, run the same command:

```sh
python install_ni_driver.py
```

The helper requests **`sudo`** access while keeping the absolute path to the environment's Python. This handles the `apt` lock-file `Permission denied` error caused by running the driver installer without administrator access. Using plain `sudo python` can select a different interpreter with no `nidaqmx` package. Keep Step 3 and analysis commands under your normal user account; the setup helper rejects `sudo` to avoid root-owned project files.

**For WSL / macOS:** skip driver installation and use these environments for analysis. The driver helper refuses WSL installation and the hardware checker reports it as outside this project's supported acquisition workflow. A Windows driver installation does not install a driver inside WSL. NI-DAQmx is unavailable for macOS.

**For Windows and native Linux:** the helper checks the DAQ Python package before launching [NI's installer](https://nidaqmx-python.readthedocs.io/en/latest/#installation). To preview the command without installing, use `python install_ni_driver.py --dry-run`. Alternatively, install the [NI-DAQmx driver](https://www.ni.com/en/support/downloads/drivers/download.ni-daq-mx.html) through the laboratory's usual IT/instructor process. Ask for assistance if you lack administrator rights, and follow any NI reboot instructions. Once installation is complete, follow [Record a measurement](#record-a-measurement-laboratory-pc) to configure and check the equipment.

## Run a Python script

**From a terminal (CLI):** complete [installation and setup](#installation-and-setup-all-operating-systems), then use the activated terminal. For a new terminal, follow [Step 4](#step-4-activate-venv-when-opening-a-new-terminal).

In that activated terminal, enter the following command and press **Enter**. Replace `my_script.py` with the file you want to run:

```sh
python my_script.py
```

For example:

```powershell
python analyse_example.py
```

**From VS Code:**

Complete the optional editor installation in [Step 1](#step-1-install-python-and-an-optional-editor), then:

1. Select **File > Open Folder** and open this project folder. For WSL, open it through the WSL extension as described in the guide linked in Step 1.
2. Press **Ctrl+Shift+P** (Windows/Linux) or **Cmd+Shift+P** (macOS), select **Python: Select Interpreter**, and choose `.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (Linux/WSL/macOS).
3. Open the script you want to run, such as `analyse_example.py`, and click the **▶ play button at the top-right of the editor**, labelled **Run Python File in Terminal**. Alternatively, right-click in the editor and select **Run > Python File in Terminal**.

Output appears in the terminal panel at the bottom of VS Code. Plots open in separate windows; close them when finished. See the [official VS Code running instructions](https://code.visualstudio.com/docs/python/run) for screenshots.

Routine measurements only require changing settings, not editing Python. For script editing and programming syntax, use [Getting started with Python in VS Code](https://code.visualstudio.com/docs/python/python-tutorial) and the [Python language tutorial](https://docs.python.org/3/tutorial/) (which assumes some programming experience).

## Check your setup

The setup helpers in [Step 3](#step-3-create-venv-and-install-project-packages) run `check_setup.py` automatically after installing packages and creating your local settings file. To check again after changing settings, moving the project or before a lab session, activate the environment using [Step 4](#step-4-activate-venv-when-opening-a-new-terminal). In the activated terminal, enter:

```sh
python check_setup.py
```

Choose the command for your situation:

| Command | When to use it |
|---|---|
| `python check_setup.py` | On your own computer for the supplied analysis and calibration exercises. NI hardware is not required. |
| `python check_setup.py --daq` | While setting up the measurement PC. Requires the DAQ Python package; an unavailable NI driver/device is reported as a warning. Setup with `daq` runs this version automatically. |
| `python check_setup.py --hardware` | On the measurement PC after installing NI-DAQmx and selecting the connected device in your settings. An unavailable driver, device or analog input is an error. |

The report prints the Python executable and settings file it is using, followed by individual checks. If Python is outside this project's `.venv`, it stops with the activation/setup command to use. It does not report the system Python's packages as errors in your project environment. Once the correct environment is selected, it checks:

- **Packages:** installed versions match the requirements, imports work, and `pip check` finds no missing or incompatible package dependencies.
- **Settings and inputs:** both settings sections are valid, the measurement calibration matches the selected channel/gain/offset/temperature, and the selected calibration CSV files and any metadata can be read and validated. It also runs the supplied example without a plot.
- **File access:** temporary files can be created, written, read, replaced and deleted in the configured recording folder and the calibration/archive folders. Local settings and the active fit calibration are checked for write access when present.
- **Plotting:** a test plot can be rendered in memory. The report names the plotting backend and warns if it cannot open windows. Run `python analyse_example.py` to check that a real plot window opens.

These checks do not fit or save a calibration or record a measurement. The file-access checks use unique temporary names, then remove their files and any newly created empty test folders. Existing recordings, settings and calibrations are preserved.

Read the status at the start of each line. In a supported terminal, `[OK]` is green, `[WARN]` is orange and `[ERROR]` is red; `[SKIP]` uses the normal text colour. Reports redirected to a file use plain text.

- **`[OK]`**: this check passed.
- **`[ERROR]`**: fix the reported problem and rerun the check. Setup stops when there are errors.
- **`[WARN]`**: review the message. For example, calibration write access is optional while `save_calibration` is `false`, and a plotting backend without windows can still run the exercises with `--no-plot`.
- **`[SKIP]`**: the check needs a missing package or valid settings, or hardware checks were not requested.

Success ends with `Check finished: 0 error(s), ... warning(s)` and `All required checks passed`. A skipped NI check is expected on an analysis-only computer. This basic check does not establish that the laboratory hardware is ready.

If a check fails, follow its `Fix:` message where provided, then rerun the same command. For package errors, rerun the setup helper; use its `daq` option for a missing `nidaqmx` package. If automatic checks fail during setup, fix the reported issue and rerun setup to finish activation. Share the complete report with your instructor if you need help.

`--hardware` additionally reads the NI driver version and checks that the configured physical device and analog inputs exist. It does not verify sensor wiring, power, calibration accuracy or an actual measurement; follow the [laboratory equipment checks](#record-a-measurement-laboratory-pc) as well. File access is checked at the time of the test, and a successful write test does not guarantee enough disk space for a later recording.

For automated use, the check returns exit code `0` when required checks pass and `1` when errors remain.

## Your settings

Edit **`user_settings.local.json`** in your editor and save before running a script. It is a complete local copy of the shared defaults in `user_settings.json`. If the local file is absent, scripts use the shared defaults and print that filename. The local file is ignored by Git, so updating the code does not overwrite your choices. Do not publish changes to shared defaults unless they should apply to everyone.

The file has one section per task. JSON uses double quotes for text, decimal points for numbers, lower-case `true`/`false`, and commas between settings. There is no comma after a section's last setting. Use `/` in folder paths. Keys beginning with `_` are explanatory notes. Scripts check syntax, types and practical limits, and name invalid settings in errors.

| `read_hotwire` setting | Meaning |
|---|---|
| `sensor` | Sensor serial number matching an available calibration, such as `"2025-6131"`. |
| `test_label` | Description included in the filename. Change it for each experiment; use `"windtunnel_0deg_aoa_15ms"` for calibration data. Avoid characters such as `/`, `:` and `?`. |
| `air_temperature_C` | Measured air temperature Tf in degrees Celsius, entered by hand. Must be below the calibrated sensor temperature Ts. |
| `measurement_time_s` | Recording duration in seconds; must be positive. |
| `sample_rate_Hz` | Requested samples per second; must be positive. Actual sampling is slower and irregular: see below. |
| `output_folder` | Folder inside this project, using `/`; default `"measurements"`. Created automatically. |
| `daq_device` | Device name shown in NI MAX, for example `"Dev1"`. |
| `daq_channels` | Inputs such as `"ai1"`, `"ai1:3"` or `"ai1, ai4"`. |
| `hotwire_channel_index` | Which input above is the hot-wire: `0` selects the first. Must match the calibration's input. |
| `show_plot` | `true` opens a plot after recording; `false` skips it. |

| `calibration_fit` setting | Meaning |
|---|---|
| `sensor` | Sensor to fit. CSV files must be in `calibration_data/<sensor>/`. |
| `voltage_column` | CSV voltage column and DAQ input, normally `"ai1"`. Its gain/offset come from `sensor_coefficients/daq_inputs.json`. |
| `air_temperature_C` | Air temperature during the recordings. All recordings in a fit must use this temperature. |
| `sensor_temperatures_C` | Fixed Ts for each sensor. Use the corrected wire temperature from its SVMtec calibration sheet. A fit at one air temperature cannot determine Ts. |
| `save_calibration` | Default **`false`**: print results and plot without saving. `true` replaces the active calibration and archives the previous file. |
| `calibration_note` | Note stored when saving. Clear it afterwards if it only applies to that fit. |
| `initial_guess`, `lower_bounds`, `upper_bounds` | Starting values and ranges for `a`, `b`, `e`. Normally leave unchanged. |
| `plot_error_bins` | Positive number of voltage bins for the plot's mean-error line. |

## Try calibration without changing the active file

1. In `calibration_fit`, select sensor `"2025-6104"`, air temperature `20.0`, voltage column `"ai1"`, and **`"save_calibration": false`**.
2. Save the settings and run:

   ```powershell
   python find_hotwire_coefficient.py
   ```

3. Expect six data files, a test RMSE near **0.050 m/s**, and `no calibration file was written`. Close the first plot to see the residual plot, then close that to finish.

For sensor `"2025-6131"`, the supplied eight files give test RMSE near **0.170 m/s**. Add `--no-plot` to either exercise's command to skip plot windows.

**RMSE** is the typical size of the difference between fitted and reference speeds, in m/s. It is not the total measurement uncertainty. Training and test samples alternate within the same recordings, so neighbouring samples are related. The leave-one-speed-out check withholds **all files at one speed**, checking prediction at a speed excluded from fitting. Sensor temperature, reference tunnel accuracy and other systematic errors also matter.

## Record a measurement (laboratory PC)

Complete [installation and setup](#installation-and-setup-all-operating-systems), including the recording package option in Step 3 and the driver installation in Step 6. Use Windows or supported native Linux for recording.

1. Follow the [SVMtec operating instructions and connector diagram](docs/Hitzdraht_doku.pdf#page=7), especially the startup sequence and handling of the delicate wire. The supplied manual describes an NI USB-6211; confirm the actual device in the lab. On Windows, use **NI Measurement & Automation Explorer (NI MAX)** to check that it appears under Devices and Interfaces and passes its self-test. On native Linux, use [NI's Linux device-configuration tools](https://www.ni.com/en/support/documentation/supplemental/18/windows-vs-desktop-linux-daqmx-experience-differences.html). Note the device name and identify the connected input.
2. In `read_hotwire`, select the actual sensor, device and channel, measure the air temperature, and set the test label and duration. Both supplied calibrations use **`ai1`**. The script refuses a different hot-wire input or changed gain/offset; refit for a new input before using it.
3. Save the settings and check the setup:

   ```powershell
   python check_setup.py --hardware
   ```

   Fix any `[ERROR]` messages before recording. The check does not take a measurement.
4. Run:

   ```powershell
   python read_hotwire.py
   ```

The script prints the selected settings and calibration before recording. **Ctrl+C** stops early. A DAQ error ends recording with an error message and keeps samples already written. The console reports the actual sample rate and output paths. Close the plot window to finish.

**Sampling limitation:** timing is controlled by the computer, rather than a hardware clock. Bundled recordings achieve about 34-37 Hz despite higher requested rates. Inspect `Runtime` for actual intervals. This script is not suitable for measuring fast fluctuations at the requested rate; those experiments need hardware-timed acquisition.

## Read and back up your results

Each run produces a pair: `..._2025-6131_my_test.csv` and `..._2025-6131_my_test.metadata.json`. Filenames include the local date/time, sensor and label; a numbered suffix avoids overwriting an existing recording.

| CSV column | Meaning |
|---|---|
| `Timestamp` | Computer's local date/time as `YYYY:MM:DD:HH:MM:SS.fraction`. Metadata creation time includes the time-zone offset. |
| `ai1` (or other channel names) | Raw input voltage in volts. |
| `Runtime` | Elapsed time since acquisition started, in seconds. |
| `v` | Calculated air velocity in m/s. |
| `U_br^2/Ts-Tf` | Historical column name for `U_br^2 / (Ts - Tf)`, in V²/°C. |

`NaN` means the formula did not give a valid finite velocity. Inspect voltage and calibration range rather than treating it as zero. Values outside the calibrated range are **extrapolated**: predictions beyond the speeds checked in the wind tunnel. Both low and high extrapolation are reported.

Metadata saves the complete measurement settings, calibration snapshot and fingerprint, script fingerprint, sample count, and completion status (`complete`, `stopped` or `failed`). Use that snapshot and its air temperature to reproduce the original conversion. Using today's active calibration instead produces a new analysis. Older CSV files without metadata do not identify their original temperature and calibration; recover those from experiment notes before recalculating.

Rows are written and flushed during recording. If the process is forcibly closed, completed rows may still be usable but metadata can remain marked `recording`; inspect it before analysing or fitting the partial run. Disk failures cannot guarantee recovery.

**Back up both files** to your course's shared storage after each experiment. Measurement CSV files, metadata and local settings are ignored by Git: neither a commit nor a GitHub download backs them up. CSV and metadata files copied into `calibration_data/` are the exception and can be tracked with their calibration.

## Fit and save a new calibration

Copy wind tunnel CSV files **and their metadata files** to `calibration_data/<sensor>/`. Names must end in a speed such as `_15ms.csv` or `_2.5ms.csv`; numbered collision suffixes such as `_15ms_1.csv` are accepted. Speeds are nominal reference values from filenames, so verify each label against the experiment. A fit needs at least three distinct speeds; use at least four for leave-one-speed-out validation, with repeats and coverage of the intended range.

Set `sensor`, `voltage_column`, temperature and Ts in `calibration_fit`. Recordings with metadata must match that sensor, channel and temperature, have status `complete` or `stopped`, and match their saved CSV fingerprint. Failed or modified runs are refused. Check a deliberately shortened run before including it. Non-finite voltages are reported and excluded; each file needs at least two finite samples.

Run first with `save_calibration: false` and inspect results with your instructor. To deliberately make the result active, set it to `true`, rerun, then set it back to `false`. The previous calibration is copied to a unique file in `sensor_coefficients/archive/` before the new file is replaced atomically. A failed save preserves the old active file. Do not edit coefficients by hand.

## Calibration reference

The formula is `v = (a + b * U_br^2 / (Ts - Tf))^e`, with `U_br = U_measured / m + Uoffset`. See [SVMtec manual, section 6.5](docs/Hitzdraht_doku.pdf#page=11). Fitting determines `a`, `b`, `e`; `m` and `Uoffset` come from the [factory test report](docs/PruefProtokoll_4CTA_7013_150427.pdf) via `daq_inputs.json`, and Ts is fixed. Optimisation uses a zero-flow extension for negative trial formula bases; measurement conversion keeps invalid bases as `NaN`.

| Sensor | Supplied calibration | Range |
|---|---|---|
| 2025-6131 | Created 07.10.2026 from recordings of 25.11.2025; test RMSE 0.17 m/s | 0-35 m/s |
| 2025-6104 | Created 07.10.2026 from recordings of 25.11.2025; test RMSE 0.05 m/s | 5-30 m/s; below 5 m/s is extrapolation |

These are the only sensors with calibration files in this download. Each JSON identifies the formula and contains coefficients, fitting method/settings, source files, hashes, software versions and per-speed errors. Covariance-based confidence intervals assume independent samples and can be optimistic; coefficient correlations and leave-one-speed-out estimates are also included.

New fingerprints use `sha256-lf-v1`: text line endings are normalised to LF before hashing; PDF bytes are unchanged. The supplied calibrations' source fingerprints were normalised on 13.10.2026, retaining original byte fingerprints. Coefficients, fit statistics and original creation dates were preserved. Their fit-script fingerprints identify the historical script, so they need not match today's modified script.

| Folder | Contents |
|---|---|
| `calibration_data/<sensor>/` | Tracked wind tunnel recordings used for fitting. |
| `sensor_coefficients/` | Active calibrations and DAQ conversions; `archive/` holds previous calibrations after saving. |
| `docs/` | [Hot-wire manual](docs/Hitzdraht_doku.pdf), [factory report](docs/PruefProtokoll_4CTA_7013_150427.pdf), and [FlowSound manual](docs/flowsound_v29_doku.pdf). |
| `measurements/` | Default recording output, ignored by Git. |

## Troubleshooting

| Problem | What to check |
|---|---|
| Python/`py` is not found | Finish installation and reopen the terminal. Verify `py -3.13 --version`; see the official guide above. |
| `git` is not found | Use the ZIP download, or install Git and reopen the terminal. |
| The environment is missing | Follow [Step 3](#step-3-create-venv-and-install-project-packages) for your operating system. |
| `./setup_venv.sh: Permission denied` on Linux/WSL | Source the helper as shown in [Step 3](#step-3-create-venv-and-install-project-packages); this also keeps `.venv` activated in your current terminal. |
| `No module named ...` | Check for `(.venv)` and follow [Step 4](#step-4-activate-venv-when-opening-a-new-terminal). If a package is still missing, rerun Step 3. |
| `No module named nidaqmx` when launching the driver installer | Select the recording command in [Step 3](#step-3-create-venv-and-install-project-packages), then continue to [Step 6](#step-6-install-the-ni-system-driver-laboratory-pc-only). The Python package and system driver are separate. |
| Check reports Python outside this project's `.venv` | Use the activation helper, or select this project's `.venv` interpreter in VS Code, then rerun the check. The report's `Python:` line shows the executable being used. |
| Installation fails or mentions long paths | Use a short local path, check internet access, and retain error text for your instructor. |
| Setup reports a file-access error | Check the named folder/file. Move the extracted project to a writable local folder, or ask your instructor about permissions. Close programs that may lock those files. |
| JSON error with a line or setting name | Edit the named file, check quotes/commas/types, save and rerun. |
| `SyntaxError` or `IndentationError` after editing Python | Use the indicated line number and the external programming guides linked above to check your changes. |
| No calibration for the sensor | Check the serial number; only the two sensors above are supplied. |
| Wrong calibration channel or gain/offset | Match the physical input to the calibration; do not bypass the check. |
| NI driver/device error | Check NI-DAQmx, USB connection, NI MAX device name and self-test. The Python package alone does not install the driver. |
| `apt` cannot open its lock file: `Permission denied` / `open (13)` | The Linux driver installer needs administrator access. Use the helper in [Step 6](#step-6-install-the-ni-system-driver-laboratory-pc-only); it requests `sudo` using this project's Python. Ask your instructor/IT if access is denied. |
| `apt` says a lock is held by another process | Wait for the other package manager to finish. Do not delete its lock files. |
| NI driver installation or hardware check is refused in WSL | Set up a separate Windows checkout and `.venv` for recording, or use a compatible native Linux measurement PC. Keep the WSL checkout for analysis. |
| Script waits after printing results | Close the plot window; calibration opens two plots in sequence. |
| PowerShell blocks activation | Run `activate_venv.bat`, which uses Command Prompt activation. No PowerShell execution-policy change is needed. |

When asking for help, include the command, complete error text, Python version, and relevant settings. For acquisition issues, include the device/channel and metadata status.

## Update or recreate the environment

For a Git download, update with `git pull --ff-only`. Local settings remain in place. If Git reports conflicting changes to tracked files, keep your work and ask your instructor before discarding anything. Repeat [Step 3](#step-3-create-venv-and-install-project-packages) when either requirements file changes, choosing the same analysis or recording option as before.

For a ZIP download, repeat Steps 2-3 in a separate folder and copy your `user_settings.local.json` into it. Keep/back up recordings and custom calibrations. Do not copy `.venv` between folders or computers.

If an environment uses an unsuitable Python version, rename `.venv` to `.venv-old`, check Step 1, and repeat Step 3. Keep the old environment until the new one works. Each computer creates its own environment; it is not downloaded from GitHub.

When adding a package for everyone, install it using the project's Python, add its name/version range to the appropriate requirements file, and commit that requirements change.

## Developer checks

With the analysis packages installed, run:

```sh
python -m unittest discover -s tests -v
```

Run this in the activated terminal. For automated Windows setup, `setup_venv.bat nopause` skips the interactive prompt and activates `.venv` in the calling Command Prompt (use `call setup_venv.bat nopause` from another batch file). Tests cover validation, sample recovery with a simulated DAQ, metadata, archival writes, calibration reproducibility, setup diagnostics and temporary-file cleanup. Driver/device checks are tested with simulated responses; the tests do not exercise physical hardware.

## License

The code is released under the [MIT License](LICENSE). Documents in `docs/` belong to their respective authors and are not covered by this license.
