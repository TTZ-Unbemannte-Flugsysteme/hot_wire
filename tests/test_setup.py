"""Setup diagnostics must report failures and leave students' files intact."""

import contextlib
import importlib.metadata
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import check_setup as check


class FileAccessTests(unittest.TestCase):
    def test_existing_files_are_unchanged_and_probes_are_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            existing = directory / "measurement.csv"
            existing.write_bytes(b"original data\n")
            check.probe_directory(directory)
            self.assertEqual(existing.read_bytes(), b"original data\n")
            self.assertEqual(list(directory.iterdir()), [existing])
            check.probe_editable_file(existing)
            self.assertEqual(existing.read_bytes(), b"original data\n")

    def test_new_nested_folders_are_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            check.probe_directory(root / "measurements" / "my_test")
            self.assertEqual(list(root.iterdir()), [])

    def test_replace_failure_is_reported_and_temporary_files_are_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(Path, "replace", side_effect=PermissionError("replacement denied")):
                with self.assertRaisesRegex(PermissionError, "replacement denied"):
                    check.probe_directory(root / "new_folder")
            self.assertEqual(list(root.iterdir()), [])

    def test_output_path_that_is_a_file_fails_without_changing_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "measurements"
            path.write_bytes(b"keep this")
            with self.assertRaises(OSError):
                check.probe_directory(path)
            self.assertEqual(path.read_bytes(), b"keep this")


class DependencyTests(unittest.TestCase):
    def test_missing_or_broken_packages_do_not_hide_other_failures(self):
        report = check.Report()
        with contextlib.redirect_stdout(io.StringIO()), \
                patch.object(check, "requirement_lines", return_value=["numpy>=2", "scipy>=1"]), \
                patch.object(check, "check_dependency", side_effect=[importlib.metadata.PackageNotFoundError("numpy"), ImportError("broken scipy binary")]), \
                patch.object(check, "check_pip", side_effect=RuntimeError("incompatible dependency")):
            installed = check.check_packages(report, False)
            self.assertEqual(report.finish(), 1)
        self.assertEqual(installed, {})
        failures = "\n".join(message for level, message in report.entries if level == "ERROR")
        self.assertIn("numpy", failures)
        self.assertIn("broken scipy binary", failures)
        self.assertIn("incompatible dependency", failures)

    def test_version_range_and_import_are_both_checked(self):
        from packaging.requirements import Requirement
        with patch.object(check.importlib.metadata, "version", return_value="1.9"), \
                patch.object(check.importlib, "import_module") as load:
            with self.assertRaisesRegex(ValueError, "requires numpy>=2"):
                check.check_dependency("numpy>=2", Requirement)
            load.assert_not_called()
        with patch.object(check.importlib.metadata, "version", return_value="2.5"), \
                patch.object(check.importlib, "import_module", side_effect=ImportError("DLL missing")):
            with self.assertRaisesRegex(ImportError, "DLL missing"):
                check.check_dependency("numpy>=2", Requirement)

    def test_daq_requirements_include_analysis_requirements(self):
        base = check.requirement_lines(check.PROJECT_DIR / "requirements.txt")
        daq = check.requirement_lines(check.PROJECT_DIR / "requirements-daq.txt")
        self.assertTrue(set(base) < set(daq))
        self.assertTrue(any(line.startswith("nidaqmx") for line in daq))


class HardwareTests(unittest.TestCase):
    def run_check(self, system, strict=True):
        report = check.Report()
        module = types.SimpleNamespace(System=types.SimpleNamespace(local=Mock(return_value=system)))
        real_import = check.importlib.import_module
        with contextlib.redirect_stdout(io.StringIO()), patch.object(check, "is_wsl", return_value=False), patch.object(check.importlib, "import_module", side_effect=lambda name: module if name == "nidaqmx.system" else real_import(name)):
            check.check_hardware(report, {"daq_device": "Dev1", "daq_channels": "ai1:2"}, strict=strict)
        return report

    def system(self, *, channels=("Dev1/ai1", "Dev1/ai2"), simulated=False):
        device = types.SimpleNamespace(dev_is_simulated=simulated, ai_physical_chans=types.SimpleNamespace(channel_names=channels))
        # A mapping with the same name-list interface as NI's collection.
        class Devices(dict):
            device_names = ["Dev1"]
        return types.SimpleNamespace(driver_version=types.SimpleNamespace(major_version=26, minor_version=0, update_version=0), devices=Devices(Dev1=device))

    def test_missing_driver_is_warning_during_setup_and_error_before_recording(self):
        class MissingDriver:
            @property
            def driver_version(self):
                raise RuntimeError("NI driver is not installed")
        for strict, level in ((False, "WARN"), (True, "ERROR")):
            report = self.run_check(MissingDriver(), strict)
            self.assertTrue(any(found == level and "NI driver is not installed" in message for found, message in report.entries))

    def test_device_and_all_channels_are_checked_without_creating_a_task(self):
        report = self.run_check(self.system())
        self.assertFalse(any(level == "ERROR" for level, _ in report.entries))
        missing_device = self.system()
        missing_device.devices.device_names = ["Dev2"]
        for system in (self.system(channels=("Dev1/ai1",)), self.system(simulated=True), missing_device):
            report = self.run_check(system)
            self.assertTrue(any(level == "ERROR" for level, _ in report.entries))


class EnvironmentTests(unittest.TestCase):
    def test_system_python_stops_before_package_or_file_checks(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(check.sys, "prefix", str(check.PROJECT_DIR.parent / "system-python")), \
                patch.object(check, "check_packages") as packages, patch.object(check, "probe_directory") as writes:
            self.assertEqual(check.main([]), 1)
        packages.assert_not_called()
        writes.assert_not_called()
        self.assertIn("outside this project's .venv", output.getvalue())
        self.assertNotIn("Package numpy", output.getvalue())

    def test_correct_venv_is_accepted(self):
        with patch.object(check.sys, "prefix", str(check.PROJECT_DIR / ".venv")):
            self.assertTrue(check.check_environment(check.Report()))

    def test_inaccessible_environment_reports_an_error_without_crashing(self):
        report = check.Report()
        with patch.object(check.sys, "prefix", str(check.PROJECT_DIR.parent / "system-python")), \
                patch.object(Path, "is_file", side_effect=PermissionError("access denied")), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(check.check_environment(report))
        self.assertTrue(any(level == "ERROR" and "access denied" in message for level, message in report.entries))

    def test_wsl_is_optional_for_analysis_and_error_for_hardware(self):
        for strict, expected in ((False, "WARN"), (True, "ERROR")):
            report = check.Report()
            with contextlib.redirect_stdout(io.StringIO()), patch.object(check, "is_wsl", return_value=True), \
                    patch.object(check.importlib, "import_module") as imports:
                check.check_hardware(report, None, strict=strict)
            imports.assert_not_called()
            self.assertTrue(any(level == expected and "WSL" in message for level, message in report.entries))


if __name__ == "__main__":
    unittest.main()
