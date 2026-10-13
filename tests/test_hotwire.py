"""Regression checks for validation, calibration provenance and DAQ failures."""

import contextlib
import copy
import csv
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

import calibration_file as calibration
import find_hotwire_coefficient as fit
import hotwire_model as model
import read_hotwire as recording
import settings_file as settings

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = json.loads((ROOT / "user_settings.json").read_text())


class SettingsTests(unittest.TestCase):
    def load(self, content, section="read_hotwire"):
        with patch.object(settings, "read_settings_file", return_value=content):
            return settings.load_settings(section)

    def test_defaults_are_valid_and_do_not_save_calibration(self):
        self.load(DEFAULTS)
        self.assertFalse(self.load(DEFAULTS, "calibration_fit")["save_calibration"])

    def test_local_copy_takes_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            default, local = (Path(folder) / name for name in ("user_settings.json", "user_settings.local.json"))
            default.write_text(json.dumps(DEFAULTS))
            own = copy.deepcopy(DEFAULTS)
            own["read_hotwire"]["test_label"] = "my_test"
            with patch.object(settings, "DEFAULT_SETTINGS_FILE", default), patch.object(settings, "LOCAL_SETTINGS_FILE", local):
                self.assertEqual(settings.load_settings("read_hotwire")["test_label"], "first_measurement")
                local.write_text(json.dumps(own))
                self.assertEqual(settings.load_settings("read_hotwire")["test_label"], "my_test")
            self.assertEqual(json.loads(default.read_text()), DEFAULTS)

    def test_invalid_shapes_have_clear_errors(self):
        for content in ([], dict(DEFAULTS, read_hotwire=[])):
            with self.assertRaisesRegex(ValueError, "JSON object"):
                self.load(content)

    def test_invalid_values_are_rejected(self):
        bad_values = {
            "sample_rate_Hz": [0, -1, float("inf"), True],
            "measurement_time_s": [0, -2, float("nan")],
            "test_label": ["", "test / 15 m/s", "test:", "trailing.", "NUL"],
            "output_folder": ["", "../outside", "C:/outside", "C:outside", "bad\\path"],
            "daq_device": ["", "Dev1/ai1"],
            "daq_channels": ["", "ai3:1", "ai1, ai1", "ai1,"],
            "hotwire_channel_index": [-1, 1],
        }
        for name, values in bad_values.items():
            for value in values:
                with self.subTest(setting=name, value=value):
                    content = copy.deepcopy(DEFAULTS)
                    content["read_hotwire"][name] = value
                    with self.assertRaises(ValueError):
                        self.load(content)

    def test_channel_expansion(self):
        self.assertEqual(settings.expand_channels("ai1:3, ai5"), ["ai1", "ai2", "ai3", "ai5"])


class ProvenanceTests(unittest.TestCase):
    def test_text_hashes_are_portable_and_binary_hashes_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            for suffix, should_match in (("csv", True), ("pdf", False)):
                path = Path(folder) / f"example.{suffix}"
                path.write_bytes(b"a,b\n1,2\n")
                expected = calibration.file_sha256(path)
                path.write_bytes(b"a,b\r\n1,2\r\n")
                self.assertEqual(calibration.file_sha256(path) == expected, should_match)

    def test_bundled_fingerprints_match(self):
        for sensor in ("2025-6104", "2025-6131"):
            source = calibration.load_calibration(sensor)["source_data"]
            self.assertEqual(source["hash_method"], calibration.HASH_METHOD)
            for item in source["files"] + source["other_sources"]:
                self.assertEqual(calibration.file_sha256(ROOT / item["file"]), item["sha256"], item["file"])
            self.assertEqual(calibration.combined_sha256([(f["file"], f["sha256"]) for f in source["files"]]), source["dataset_sha256"])

    def test_failed_save_keeps_old_active_calibration(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            active = directory / "sensor.json"
            old = {"coefficients": {"a": 1}}
            calibration.write_json(active, old)
            with patch.object(calibration, "CALIBRATION_DIR", directory), patch.object(calibration, "ARCHIVE_DIR", directory / "archive"):
                with self.assertRaises(ValueError):
                    calibration.save_calibration("sensor", {"bad": float("nan")})
            self.assertEqual(json.loads(active.read_text()), old)
            self.assertEqual(json.loads(next((directory / "archive").glob("*.json")).read_text()), old)
            self.assertFalse(list(directory.glob("*.tmp")))

    def test_archives_do_not_collide(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            calibration.write_json(directory / "sensor.json", {"version": 0})
            with patch.object(calibration, "CALIBRATION_DIR", directory), patch.object(calibration, "ARCHIVE_DIR", directory / "archive"), patch.object(calibration, "datetime") as clock:
                clock.now.return_value = datetime(2026, 10, 13, 12)
                calibration.save_calibration("sensor", {"version": 1})
                calibration.save_calibration("sensor", {"version": 2})
            versions = [json.loads(path.read_text())["version"] for path in (directory / "archive").glob("*.json")]
            self.assertEqual(sorted(versions), [0, 1])


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        fit.configure(copy.deepcopy(DEFAULTS["calibration_fit"]))

    def test_both_supplied_calibrations_reproduce_results(self):
        for sensor in ("2025-6104", "2025-6131"):
            own = dict(DEFAULTS["calibration_fit"], sensor=sensor)
            fit.configure(own)
            with contextlib.redirect_stdout(io.StringIO()):
                files = fit.find_speed_files(fit.DATA_DIR)
                values, _ = fit.load_measurements(files, "ai1")
            u, speed = fit.combine_files(files, values)
            params, covariance = fit.fit_coefficients(u[::2], speed[::2], fit.INITIAL_GUESS)
            saved = calibration.load_calibration(sensor)
            np.testing.assert_allclose(params, [saved["coefficients"][name] for name in fit.PARAMETER_NAMES], atol=2e-5, rtol=0)
            statistics = fit.calculate_statistics(params, covariance, files, values, u[::2], speed[::2], u[1::2], speed[1::2])
            self.assertAlmostEqual(statistics["rmse_test_m_per_s"], saved["statistics"]["rmse_test_m_per_s"], places=5)
            self.assertEqual(len(statistics["leave_one_speed_out_fits"]), len(set(files.values())))

    def test_all_repeats_of_a_speed_are_withheld(self):
        files = {Path("first_10ms.csv"): 10, Path("second_10ms.csv"): 10, Path("third_20ms.csv"): 20, Path("fourth_30ms.csv"): 30}
        values = {path: np.ones(6) for path in files}
        seen = []

        def refit(u, speeds, start):
            seen.append(set(speeds))
            return np.array([1., 2., 3.]), np.eye(3)

        with patch.object(fit, "fit_coefficients", side_effect=refit), patch.object(fit, "model", side_effect=lambda voltage, *params: np.ones_like(voltage)):
            results = fit.leave_one_speed_out(files, values, [1, 2, 3])
        self.assertEqual(set(results), {10, 20, 30})
        self.assertEqual(seen, [{20, 30}, {10, 30}, {10, 20}])

    def test_decimal_speed_and_collision_suffixes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name in ("run_2.5ms.csv", "run_15ms.csv", "run_15ms_1.csv"):
                (directory / name).touch()
            self.assertEqual(sorted(fit.find_speed_files(directory).values()), [2.5, 15., 15.])

    def test_empty_voltage_data_has_clear_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run_15ms.csv"
            path.write_text("ai1\nnan\ninf\n")
            with self.assertRaisesRegex(ValueError, "two finite"):
                fit.load_measurements({path: 15}, "ai1")

    def test_practice_run_never_saves(self):
        with patch.object(fit, "load_settings", return_value=copy.deepcopy(DEFAULTS["calibration_fit"])), patch.object(fit, "save_calibration") as save, contextlib.redirect_stdout(io.StringIO()):
            fit.main(show_plots=False)
        save.assert_not_called()

    def test_recording_metadata_checks_temperature_and_csv_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run_15ms.csv"
            path.write_text("ai1\n2.0\n2.1\n")
            metadata = {"status": "complete", "settings": {"sensor": "2025-6104", "air_temperature_C": 20},
                        "hotwire_channel": "ai1", "hash_method": calibration.HASH_METHOD,
                        "csv_sha256": calibration.file_sha256(path)}
            calibration.write_json(path.with_suffix(".metadata.json"), metadata)
            with contextlib.redirect_stdout(io.StringIO()):
                values, descriptions = fit.load_measurements({path: 15}, "ai1")
            self.assertEqual(len(values[path]), 2)
            self.assertIn("metadata_sha256", descriptions[0])
            metadata["settings"]["air_temperature_C"] = 21
            calibration.write_json(path.with_suffix(".metadata.json"), metadata)
            with self.assertRaisesRegex(ValueError, "air temperature"):
                fit.load_measurements({path: 15}, "ai1")
            metadata["settings"]["air_temperature_C"] = 20
            calibration.write_json(path.with_suffix(".metadata.json"), metadata)
            path.write_text("ai1\n2.0\n2.1\n2.2\n")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                fit.load_measurements({path: 15}, "ai1")


class ConversionTests(unittest.TestCase):
    def test_bad_temperature_or_coefficients_are_rejected(self):
        coeffs = calibration.load_calibration("2025-6104")["coefficients"]
        for temperature in (coeffs["Ts"], coeffs["Ts"] + 1, float("nan")):
            with self.assertRaises(ValueError):
                model.voltage_to_velocity([2], coeffs, temperature)
        for name, value in (("m", 0), ("a", float("inf")), ("e", -1)):
            with self.assertRaises(ValueError):
                model.voltage_to_velocity([2], dict(coeffs, **{name: value}), 20)

    def test_scalar_and_invalid_flow(self):
        coeffs = calibration.load_calibration("2025-6104")["coefficients"]
        velocity, _ = model.voltage_to_velocity(2., coeffs, 20)
        self.assertTrue(np.isfinite(velocity))
        velocity, _ = model.voltage_to_velocity([-3., float("inf")], coeffs, 20)
        self.assertTrue(np.isnan(velocity).all())
        velocity, _ = model.voltage_to_velocity([-3.], coeffs, 20, clip_negative=True)
        self.assertEqual(float(velocity[0]), 0)

    def test_low_and_high_extrapolation(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            recording.warn_if_outside_calibration(np.array([1., 40.]), calibration.load_calibration("2025-6104"))
        self.assertIn("below", output.getvalue())
        self.assertIn("above", output.getvalue())

    def test_helpers_and_example_work_without_daq_package(self):
        code = """
import builtins
original = builtins.__import__
def without_daq(name, *args, **kwargs):
    if name.startswith('nidaqmx'):
        raise ImportError('DAQ package intentionally absent')
    return original(name, *args, **kwargs)
builtins.__import__ = without_daq
import analyse_example, read_hotwire, find_hotwire_coefficient
analyse_example.main(show_plot=False)
"""
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Mean velocity: 14.976", result.stdout)


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.own = dict(DEFAULTS["read_hotwire"], show_plot=False, measurement_time_s=1)
        self.task = Mock()
        self.task.__enter__ = Mock(return_value=self.task)
        self.task.__exit__ = Mock(return_value=False)
        self.daq = types.ModuleType("nidaqmx")
        self.daq.Task = Mock(return_value=self.task)
        ni_error = type("FakeNiError", (Exception,), {})
        self.daq.errors = types.SimpleNamespace(Error=ni_error, DaqError=type("FakeDaqError", (ni_error,), {}),
                                              DaqNotFoundError=type("FakeDriverError", (ni_error,), {}))
        constants = types.ModuleType("nidaqmx.constants")
        constants.TerminalConfiguration = types.SimpleNamespace(RSE="RSE")
        for patcher in (patch.dict(sys.modules, {"nidaqmx": self.daq, "nidaqmx.constants": constants}),
                        patch.object(recording, "PROJECT_DIR", self.root),
                        patch.object(recording, "load_settings", return_value=self.own), patch.object(recording.time, "sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def results(self):
        path = next((self.root / "measurements").glob("*.csv"))
        with path.open(newline="") as file:
            rows = list(csv.DictReader(file))
        return path, rows, json.loads(path.with_suffix(".metadata.json").read_text())

    def test_disconnect_keeps_flushed_samples_and_provenance(self):
        calls = 0

        def read():
            nonlocal calls
            calls += 1
            if calls == 1:
                return 2.
            self.assertEqual(len(self.results()[1]), 1, "Sample must be on disk before the next DAQ read")
            raise self.daq.errors.DaqError("Device disconnected")

        self.task.read.side_effect = read
        with self.assertRaisesRegex(RuntimeError, "partial CSV"), contextlib.redirect_stdout(io.StringIO()):
            recording.main()
        path, rows, metadata = self.results()
        self.assertEqual(metadata["status"], "failed")
        self.assertEqual(metadata["samples"], 1)
        self.assertEqual(float(rows[0]["ai1"]), 2.)
        self.assertEqual(metadata["settings"]["air_temperature_C"], 20)
        self.assertEqual(metadata["calibration"]["sensor"], "2025-6131")
        self.assertEqual(metadata["csv_sha256"], calibration.file_sha256(path))
        velocity, _ = model.voltage_to_velocity(2., metadata["calibration"]["coefficients"], 20)
        self.assertAlmostEqual(float(rows[0]["v"]), float(velocity))

    def test_ctrl_c_saves_stopped_status(self):
        self.task.read.side_effect = [2., KeyboardInterrupt()]
        with contextlib.redirect_stdout(io.StringIO()):
            recording.main()
        _, rows, metadata = self.results()
        self.assertEqual(len(rows), 1)
        self.assertEqual(metadata["status"], "stopped")

    def test_complete_run_and_multi_channel_names(self):
        self.own["daq_channels"] = "ai1, ai4"
        self.task.read.side_effect = [[2., 3.], [2.1, 3.1]]
        with patch.object(recording.time, "perf_counter", side_effect=[0., 1., 1.1, 1.2, 1.3, 1.4, 2.1, 2.2]), contextlib.redirect_stdout(io.StringIO()):
            recording.main()
        self.task.ai_channels.add_ai_voltage_chan.assert_called_once_with("Dev1/ai1,Dev1/ai4", terminal_config="RSE", min_val=-10., max_val=10.)
        _, rows, metadata = self.results()
        self.assertEqual(metadata["status"], "complete")
        self.assertEqual(len(rows), 2)
        self.assertEqual(float(rows[1]["ai4"]), 3.1)
        self.assertAlmostEqual(metadata["achieved_sample_rate_Hz"], 5.)

    def test_wrong_channel_or_temperature_never_opens_daq(self):
        for changes in ({"daq_channels": "ai0"}, {"air_temperature_C": 200}):
            with patch.object(recording, "load_settings", return_value=dict(self.own, **changes)), self.assertRaises(ValueError), contextlib.redirect_stdout(io.StringIO()):
                recording.main()
        self.daq.Task.assert_not_called()
        self.assertFalse((self.root / "measurements").exists())

    def test_no_samples_records_failure(self):
        self.task.read.side_effect = self.daq.errors.DaqError("Device unavailable")
        with self.assertRaisesRegex(RuntimeError, "No samples"), contextlib.redirect_stdout(io.StringIO()):
            recording.main()
        _, rows, metadata = self.results()
        self.assertEqual(rows, [])
        self.assertEqual(metadata["status"], "failed")
        self.assertEqual(metadata["samples"], 0)

    def test_missing_driver_has_clear_error_and_failure_metadata(self):
        self.task.__enter__.side_effect = self.daq.errors.DaqNotFoundError("NI-DAQmx driver is not installed")
        with self.assertRaisesRegex(RuntimeError, "driver is not installed"), contextlib.redirect_stdout(io.StringIO()):
            recording.main()
        _, rows, metadata = self.results()
        self.assertEqual(rows, [])
        self.assertEqual(metadata["status"], "failed")
        self.assertIn("driver is not installed", metadata["error"])


if __name__ == "__main__":
    unittest.main()
