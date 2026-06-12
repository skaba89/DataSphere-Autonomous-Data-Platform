"""Tests for scripts/bump_version.py"""

import re
import sys
import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers to load the script as a module without executing main()
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
REPO_ROOT = Path(__file__).parent.parent


def _load_bump_version():
    """Import bump_version.py as a module."""
    spec = importlib.util.spec_from_file_location(
        "bump_version", SCRIPTS_DIR / "bump_version.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bv = _load_bump_version()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_read_current_version():
    """read_current_version() should return the version declared in pyproject.toml."""
    version = bv.read_current_version()
    # Must be a valid X.Y.Z string
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"Unexpected version: {version}"
    # Must match what pyproject.toml actually says
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
    assert m is not None
    assert version == m.group(1)


def test_bump_patch():
    """patch bump increments the third component and resets nothing."""
    assert bv.bump("1.2.0", "patch") == "1.2.1"
    assert bv.bump("0.0.9", "patch") == "0.0.10"


def test_bump_minor():
    """minor bump increments the second component and resets patch to 0."""
    assert bv.bump("1.2.3", "minor") == "1.3.0"
    assert bv.bump("2.9.5", "minor") == "2.10.0"


def test_bump_major():
    """major bump increments the first component and resets minor/patch to 0."""
    assert bv.bump("1.2.3", "major") == "2.0.0"
    assert bv.bump("0.9.9", "major") == "1.0.0"


def test_explicit_version():
    """An explicit version string is passed through unchanged."""
    assert bv.bump("1.2.0", "1.5.0") == "1.5.0"
    assert bv.bump("0.0.1", "3.0.0") == "3.0.0"


def test_invalid_version_raises():
    """A non-semver, non-bump-type string raises ValueError."""
    with pytest.raises(ValueError):
        bv.bump("1.2.0", "notaversion")

    with pytest.raises(ValueError):
        bv.bump("1.2.0", "1.2")  # missing patch component

    with pytest.raises(ValueError):
        bv.bump("1.2.0", "1.a.3")  # non-numeric component


def test_update_file_modifies_correctly(tmp_path):
    """update_file() replaces the version in the matched pattern region."""
    sample = tmp_path / "sample.toml"
    sample.write_text('[project]\nversion = "1.2.0"\nname = "foo"\n')

    changed = bv.update_file(sample, "1.2.0", "1.3.0", r'version\s*=\s*"[^"]+"')

    assert changed is True
    content = sample.read_text()
    assert 'version = "1.3.0"' in content
    assert '1.2.0' not in content


def test_update_file_returns_false_when_no_match(tmp_path):
    """update_file() returns False when the pattern does not match."""
    sample = tmp_path / "other.txt"
    sample.write_text("nothing relevant here\n")

    changed = bv.update_file(sample, "1.2.0", "1.3.0", r'version\s*=\s*"[^"]+"')
    assert changed is False
    assert sample.read_text() == "nothing relevant here\n"


def test_script_runs_without_error():
    """bump() function is callable directly and returns the expected result."""
    result = bv.bump("2.0.0", "patch")
    assert result == "2.0.1"

    result = bv.bump("2.0.0", "minor")
    assert result == "2.1.0"

    result = bv.bump("2.0.0", "major")
    assert result == "3.0.0"


def test_changelog_exists_and_has_unreleased_section():
    """CHANGELOG.md exists and contains the [Unreleased] section."""
    changelog = REPO_ROOT / "CHANGELOG.md"
    assert changelog.exists(), "CHANGELOG.md does not exist"
    content = changelog.read_text()
    assert "## [Unreleased]" in content, "Missing [Unreleased] section in CHANGELOG.md"


def test_changelog_has_v120_section():
    """CHANGELOG.md contains a [1.2.0] release section."""
    changelog = REPO_ROOT / "CHANGELOG.md"
    content = changelog.read_text()
    assert "## [1.2.0]" in content, "Missing [1.2.0] section in CHANGELOG.md"
