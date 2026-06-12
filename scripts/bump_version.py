#!/usr/bin/env python3
"""
Bump DataSphere version across all version-bearing files.

Usage:
    python scripts/bump_version.py patch    # 1.2.0 -> 1.2.1
    python scripts/bump_version.py minor    # 1.2.0 -> 1.3.0
    python scripts/bump_version.py major    # 1.2.0 -> 2.0.0
    python scripts/bump_version.py 1.5.0   # explicit version
    python scripts/bump_version.py patch --tag  # bump and create git tag
"""

import re
import sys
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read_current_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    return m.group(1) if m else "1.0.0"


def bump(version: str, bump_type: str) -> str:
    """Calculate new version string from current version and bump type."""
    if bump_type in ("major", "minor", "patch"):
        major, minor, patch = map(int, version.split("."))
        if bump_type == "major":
            return f"{major + 1}.0.0"
        elif bump_type == "minor":
            return f"{major}.{minor + 1}.0"
        else:
            return f"{major}.{minor}.{patch + 1}"
    else:
        # Treat as explicit version string
        parts = bump_type.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(
                f"Invalid version or bump type: '{bump_type}'. "
                "Use 'major', 'minor', 'patch', or an explicit X.Y.Z string."
            )
        return bump_type


def update_file(path: Path, old: str, new: str, pattern: str) -> bool:
    """Replace occurrences of old version with new version in file, guided by pattern."""
    content = path.read_text()
    new_content = re.sub(
        pattern, lambda m: m.group(0).replace(old, new), content
    )
    if new_content != content:
        path.write_text(new_content)
        return True
    return False


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    bump_type = sys.argv[1]
    create_tag = "--tag" in sys.argv

    current = read_current_version()
    new_version = bump(current, bump_type)

    print(f"Bumping {current} -> {new_version}")

    # --- pyproject.toml ---
    changed = update_file(
        ROOT / "pyproject.toml",
        current,
        new_version,
        r'version\s*=\s*"[^"]+"',
    )
    print(f"  {'✓' if changed else '–'} pyproject.toml")

    # --- datasphere/api/app.py ---
    app_py = ROOT / "datasphere" / "api" / "app.py"
    if app_py.exists():
        changed = update_file(
            app_py,
            current,
            new_version,
            r'_VERSION\s*=\s*"[^"]+"',
        )
        print(f"  {'✓' if changed else '–'} datasphere/api/app.py")
    else:
        print("  – datasphere/api/app.py (not found, skipped)")

    # --- infra/helm/datasphere/Chart.yaml ---
    chart = ROOT / "infra" / "helm" / "datasphere" / "Chart.yaml"
    if chart.exists():
        content = chart.read_text()
        content = re.sub(r'(version:\s*)[\d.]+', rf'\g<1>{new_version}', content)
        content = re.sub(
            r'(appVersion:\s*)"[\d.]+"', rf'\g<1>"{new_version}"', content
        )
        chart.write_text(content)
        print("  ✓ infra/helm/datasphere/Chart.yaml")
    else:
        print("  – infra/helm/datasphere/Chart.yaml (not found, skipped)")

    # --- README.md badge ---
    readme = ROOT / "README.md"
    if readme.exists():
        content = readme.read_text()
        new_content = re.sub(r'version-[\d.]+-', f'version-{new_version}-', content)
        if new_content != content:
            readme.write_text(new_content)
            print("  ✓ README.md")
        else:
            print("  – README.md (no version badge found)")
    else:
        print("  – README.md (not found, skipped)")

    # --- CHANGELOG.md new section ---
    changelog = ROOT / "CHANGELOG.md"
    if changelog.exists():
        today = date.today().isoformat()
        new_entry = (
            f"\n## [{new_version}] - {today}\n\n"
            "### Added\n- <!-- describe changes -->\n\n"
            "### Changed\n- <!-- describe changes -->\n\n"
            "### Fixed\n- <!-- describe changes -->\n\n"
        )
        content = changelog.read_text()
        if f"## [{new_version}]" in content:
            print(f"  – CHANGELOG.md (section [{new_version}] already exists)")
        else:
            content = content.replace(
                "## [Unreleased]\n", f"## [Unreleased]\n{new_entry}"
            )
            changelog.write_text(content)
            print("  ✓ CHANGELOG.md (new section added)")
    else:
        print("  – CHANGELOG.md (not found, skipped)")

    # --- Optional git tag ---
    if create_tag:
        subprocess.run(["git", "tag", f"v{new_version}"], check=True)
        print(f"  ✓ git tag v{new_version}")

    print(f"\nDone! New version: {new_version}")
    print("Next: fill in CHANGELOG.md entries, then commit and push.")


if __name__ == "__main__":
    main()
