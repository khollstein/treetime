#!/usr/bin/env python3
"""
Treetime release script
-----------------------
Usage:  python release.py

What it does:
  1. Reads the current version from config.py
  2. Runs PyInstaller to build the app bundle
  3. Runs Inno Setup to compile the installer
  4. Creates a GitHub Release (tag = v<version>) and uploads TreetimeSetup.exe

Requirements:
  - Inno Setup 6 installed at the default path
  - GitHub CLI (gh) installed and authenticated  (`gh auth login` once)
  - PyInstaller installed in the current Python env

Run `gh auth login` once before using this script.
"""

import subprocess
import sys
import re
from pathlib import Path

ROOT = Path(__file__).parent
ISCC = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
INSTALLER = ROOT / "installer_output" / "TreetimeSetup.exe"
ICON = ROOT / "treetime.ico"
INSTALLER_ISS = ROOT / "installer.iss"

# gh CLI — prefers system PATH, falls back to portable install location
def _find_gh() -> str:
    import shutil
    # First: check next to this script (most reliable across user contexts)
    local = ROOT / "gh.exe"
    if local.exists():
        return str(local)
    on_path = shutil.which("gh")
    if on_path:
        return on_path
    sys.exit(
        "gh.exe not found in the project folder or PATH.\n"
        "Make sure gh.exe is in the same folder as release.py."
    )

GH = _find_gh()


def run(cmd, **kwargs):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, check=True, **kwargs)
    return result


def get_version() -> str:
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', config)
    if not m:
        sys.exit("Could not read APP_VERSION from config.py")
    return m.group(1)


def check_gh():
    # Check auth status
    result = subprocess.run(
        [GH, "auth", "status"], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit(
            "Not authenticated with GitHub.\n"
            f"Run:  \"{GH}\" auth login\n"
            "and follow the browser prompts, then re-run this script."
        )


def build_pyinstaller():
    run([
        sys.executable, "-m", "PyInstaller",
        "--name", "Treetime",
        "--windowed",
        "--onedir",
        f"--icon={ICON}",
        "-y",
        str(ROOT / "main.py"),
    ], cwd=ROOT)


def build_installer():
    if not ISCC.exists():
        sys.exit(f"Inno Setup not found at {ISCC}")
    run([str(ISCC), str(INSTALLER_ISS)], cwd=ROOT)
    if not INSTALLER.exists():
        sys.exit("Installer was not created — check Inno Setup output above.")


def create_github_release(version: str):
    tag = f"v{version}"
    notes = (
        f"## Treetime {tag}\n\n"
        "**Install:** Download `TreetimeSetup.exe` and run it.\n\n"
        "See commit history for full change log."
    )
    # Delete existing release/tag if it exists (allows re-running on same version)
    subprocess.run(
        [GH, "release", "delete", tag, "--yes"],
        capture_output=True, cwd=ROOT
    )
    run([
        GH, "release", "create", tag,
        str(INSTALLER),
        "--title", f"Treetime {tag}",
        "--notes", notes,
    ], cwd=ROOT)


if __name__ == "__main__":
    version = get_version()
    print(f"Building Treetime v{version}")

    check_gh()
    build_pyinstaller()
    build_installer()
    create_github_release(version)

    print(f"\nDone! Treetime v{version} released.")
    print(f"Download: https://github.com/khollstein/treetime/releases/tag/v{version}")
