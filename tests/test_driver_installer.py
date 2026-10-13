"""Driver installation must use the venv and never elevate Python package setup."""

import contextlib
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import install_ni_driver as driver


class DriverInstallerTests(unittest.TestCase):
    def configured(self, system="linux", uid=1000, package_returncode=0):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(driver.sys, "platform", system))
        stack.enter_context(patch.object(driver, "is_wsl", return_value=False))
        stack.enter_context(patch.object(Path, "is_file", return_value=True))
        stack.enter_context(patch.object(driver.os, "geteuid", return_value=uid, create=True))
        stack.enter_context(patch.object(driver.shutil, "which", return_value="/usr/bin/sudo"))
        run = stack.enter_context(patch.object(driver.subprocess, "run", return_value=subprocess.CompletedProcess([], package_returncode, "", "missing nidaqmx")))
        return run

    def test_linux_sudo_keeps_venv_python_path_without_resolving_symlink(self):
        run = self.configured()
        command = driver.installer_command()
        self.assertEqual(command, ["/usr/bin/sudo", "--", str(driver.PROJECT_DIR / ".venv/bin/python"), "-m", "nidaqmx", "installdriver"])
        self.assertEqual(run.call_args.args[0][0], command[2])

    def test_windows_and_linux_root_do_not_request_sudo(self):
        for system, relative in (("win32", ".venv/Scripts/python.exe"), ("linux", ".venv/bin/python")):
            with self.subTest(system=system):
                self.configured(system, uid=0)
                self.assertEqual(driver.installer_command(), [str(driver.PROJECT_DIR / relative), "-m", "nidaqmx", "installdriver"])

    def test_missing_package_stops_before_installation(self):
        run = self.configured(package_returncode=1)
        with self.assertRaisesRegex(RuntimeError, "setup_venv.sh daq"):
            driver.installer_command()
        self.assertEqual(run.call_count, 1)

    def test_wsl_refuses_system_driver_installation(self):
        run = self.configured()
        with patch.object(driver, "is_wsl", return_value=True), self.assertRaisesRegex(RuntimeError, "WSL detected"):
            driver.installer_command()
        run.assert_not_called()

    def test_dry_run_does_not_launch_installer(self):
        run = self.configured()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(driver.main(["--dry-run"]), 0)
        self.assertEqual(run.call_count, 1)  # Only the package import probe.

    def test_installer_failure_is_nonzero_with_admin_guidance(self):
        run = self.configured()
        run.side_effect = [subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 100)]
        errors = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            self.assertEqual(driver.main([]), 1)
        self.assertIn("administrator access", errors.getvalue())
        self.assertIn("Do not delete lock files", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
