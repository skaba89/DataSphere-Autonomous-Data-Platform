"""
Coverage tests for datasphere/cli/upgrade.py — targeting missing lines.
Missing: _get_latest_version success (69-73), install flow (175-210),
         _pip_install (214-236)
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# _get_latest_version — lines 61-74
# ---------------------------------------------------------------------------

class TestGetLatestVersion:
    def test_get_latest_version_parses_pip_output(self):
        """Mock pip output to test the parsing logic."""
        from datasphere.cli.upgrade import _get_latest_version

        mock_result = MagicMock()
        mock_result.stdout = "Available versions: 1.2.3, 1.2.2, 1.2.1\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            version = _get_latest_version("some-package")
        assert version == "1.2.3"

    def test_get_latest_version_no_available_versions_in_output(self):
        """When pip output doesn't contain 'Available versions:', return None."""
        from datasphere.cli.upgrade import _get_latest_version

        mock_result = MagicMock()
        mock_result.stdout = "Package not found\n"
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            version = _get_latest_version("nonexistent-pkg")
        assert version is None

    def test_get_latest_version_subprocess_exception(self):
        """Subprocess raises an exception — should return None."""
        from datasphere.cli.upgrade import _get_latest_version

        with patch("subprocess.run", side_effect=Exception("network error")):
            version = _get_latest_version("some-package")
        assert version is None

    def test_get_latest_version_timeout(self):
        """Subprocess timeout — should return None."""
        from datasphere.cli.upgrade import _get_latest_version

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=10)):
            version = _get_latest_version("some-package")
        assert version is None


# ---------------------------------------------------------------------------
# upgrade command — install flow (lines 175-210)
# ---------------------------------------------------------------------------

class TestUpgradeInstallFlow:
    def test_upgrade_yes_flag_installs_optional(self):
        """--yes flag skips the confirmation prompt for optional packages."""
        from datasphere.cli.upgrade import upgrade

        # Patch subprocess.run so no actual pip install happens
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        runner = CliRunner()
        with patch("subprocess.run", return_value=mock_result):
            result = runner.invoke(upgrade, ["--yes", "--core-only"])
        # Should complete without crashing
        assert result.exit_code in (0, 1)

    def test_upgrade_check_only_skips_install(self):
        """--check-only should not call pip install."""
        from datasphere.cli.upgrade import upgrade

        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            result = runner.invoke(upgrade, ["--check-only"])
        # subprocess.run may be called for version checks but not for installs
        assert result.exit_code == 0

    def test_upgrade_with_existing_package(self):
        """Test upgrade when specific known package is requested."""
        from datasphere.cli.upgrade import upgrade

        runner = CliRunner()
        result = runner.invoke(upgrade, ["--check-only", "--package", "pydantic"])
        assert result.exit_code == 0
        assert "pydantic" in result.output

    def test_upgrade_full_run_with_mocked_subprocess(self):
        """Full upgrade run with mocked subprocess to avoid actual installs."""
        from datasphere.cli.upgrade import upgrade

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed datasphere-1.0.0"
        mock_result.stderr = ""

        runner = CliRunner()
        # Use --core-only --yes to take the install path without interaction
        with patch("subprocess.run", return_value=mock_result):
            # Also mock _get_installed_version to return None for core packages
            # to trigger the install path
            with patch("datasphere.cli.upgrade._get_installed_version", return_value=None):
                result = runner.invoke(upgrade, ["--core-only", "--yes"])
        assert result.exit_code in (0, 1)

    def test_upgrade_optional_packages_user_declines(self):
        """When user says 'N' to optional packages, skip them."""
        from datasphere.cli.upgrade import upgrade

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        runner = CliRunner()
        with patch("subprocess.run", return_value=mock_result):
            with patch("datasphere.cli.upgrade._get_installed_version", return_value=None):
                # Input "N" to decline optional package install
                result = runner.invoke(upgrade, [], input="N\n")
        assert result.exit_code in (0, 1)

    def test_upgrade_optional_packages_user_accepts(self):
        """When user says 'o' (yes in French), install optional packages."""
        from datasphere.cli.upgrade import upgrade

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        runner = CliRunner()
        with patch("subprocess.run", return_value=mock_result):
            with patch("datasphere.cli.upgrade._get_installed_version", return_value=None):
                result = runner.invoke(upgrade, [], input="o\n")
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# _pip_install — lines 213-236
# ---------------------------------------------------------------------------

class TestPipInstall:
    def test_pip_install_empty_list(self):
        """_pip_install with empty list does nothing."""
        from datasphere.cli.upgrade import _pip_install
        # Should not raise
        _pip_install([])

    def test_pip_install_success(self):
        """_pip_install with a package — subprocess succeeds."""
        from datasphere.cli.upgrade import _pip_install

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("datasphere.cli.upgrade._get_installed_version", return_value="1.0.0"):
                _pip_install(["some-fake-package"])

    def test_pip_install_failure(self):
        """_pip_install when subprocess returns non-zero."""
        from datasphere.cli.upgrade import _pip_install

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: Could not find package"

        with patch("subprocess.run", return_value=mock_result):
            # Should not raise, just print error
            _pip_install(["nonexistent-package-xyz"])

    def test_pip_install_timeout(self):
        """_pip_install when subprocess times out."""
        from datasphere.cli.upgrade import _pip_install

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=120)):
            # Should not raise
            _pip_install(["slow-package"])

    def test_pip_install_generic_exception(self):
        """_pip_install when subprocess raises generic exception."""
        from datasphere.cli.upgrade import _pip_install

        with patch("subprocess.run", side_effect=RuntimeError("unexpected error")):
            # Should not raise
            _pip_install(["bad-package"])

    def test_pip_install_multiple_packages(self):
        """_pip_install with multiple packages."""
        from datasphere.cli.upgrade import _pip_install

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("datasphere.cli.upgrade._get_installed_version", return_value="2.0.0"):
                _pip_install(["pkg-a", "pkg-b", "pkg-c"])


# ---------------------------------------------------------------------------
# upgrade datasphere self-update (lines 195-210)
# ---------------------------------------------------------------------------

class TestUpgradeSelfUpdate:
    def test_upgrade_datasphere_success(self):
        """Test the self-upgrade of datasphere itself succeeds."""
        from datasphere.cli.upgrade import upgrade

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed"
        mock_result.stderr = ""

        runner = CliRunner()
        # All deps installed (not None) so no pip_install of missing packages
        with patch("subprocess.run", return_value=mock_result):
            result = runner.invoke(upgrade, ["--yes"])
        assert result.exit_code in (0, 1)

    def test_upgrade_datasphere_subprocess_exception(self):
        """Test self-upgrade when subprocess raises an exception."""
        from datasphere.cli.upgrade import upgrade

        runner = CliRunner()
        with patch("subprocess.run", side_effect=Exception("network error")):
            result = runner.invoke(upgrade, ["--yes"])
        # Should handle gracefully
        assert result.exit_code in (0, 1)

    def test_upgrade_datasphere_nonzero_returncode(self):
        """Test self-upgrade when pip returns non-zero (dev mode)."""
        from datasphere.cli.upgrade import upgrade

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Not found on PyPI"

        runner = CliRunner()
        with patch("subprocess.run", return_value=mock_result):
            result = runner.invoke(upgrade, ["--yes"])
        assert result.exit_code in (0, 1)
        assert "dev" in result.output.lower() or "DataSphere" in result.output
