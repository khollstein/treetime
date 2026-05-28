#!/usr/bin/env python3
"""
Treetime release script
-----------------------
Usage:  python release.py

First-time setup:
  1. Go to https://github.com/settings/tokens/new
  2. Note: "Treetime release"
  3. Expiration: No expiration  (or 1 year)
  4. Scope: tick "repo" (top-level checkbox)
  5. Click "Generate token" and copy it
  6. Paste it when this script asks, or save it in a file called
     GITHUB_TOKEN in this folder (one line, the token only).

What this script does every run:
  1. Reads version from config.py
  2. Builds with PyInstaller
  3. Compiles installer with Inno Setup
  4. Creates/updates a GitHub Release and uploads TreetimeSetup.exe
"""

import json
import re
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT       = Path(__file__).parent
ISCC       = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
INSTALLER  = ROOT / "installer_output" / "TreetimeSetup.exe"
ICON       = ROOT / "treetime.ico"
ISS        = ROOT / "installer.iss"
TOKEN_FILE = ROOT / "GITHUB_TOKEN"
REPO       = "khollstein/treetime"


# ── Helpers ────────────────────────────────────────────────────────────

def run(cmd, **kwargs):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def get_version() -> str:
    text = (ROOT / "config.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    if not m:
        sys.exit("Could not read APP_VERSION from config.py")
    return m.group(1)


def get_token() -> str:
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    print("\n" + "="*60)
    print("GitHub Personal Access Token required.")
    print("="*60)
    print("Create one at: https://github.com/settings/tokens/new")
    print("  Note:       Treetime release")
    print("  Expiration: No expiration")
    print("  Scope:      tick 'repo' (the top checkbox)")
    print("Then paste it below (it starts with 'ghp_').")
    print("It will be saved to GITHUB_TOKEN in this folder.\n")
    token = input("Paste token: ").strip()
    if not token:
        sys.exit("No token provided.")
    TOKEN_FILE.write_text(token, encoding="utf-8")
    print("Token saved to GITHUB_TOKEN — won't be asked again.")
    return token


def gh_api(method: str, path: str, token: str, body=None,
           content_type="application/json") -> dict:
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="replace")
        sys.exit(f"GitHub API error {e.code}: {body_txt}")


def upload_asset(upload_url: str, token: str, filepath: Path):
    # upload_url looks like: https://uploads.github.com/...{?name,label}
    url = upload_url.split("{")[0] + f"?name={filepath.name}"
    data = filepath.read_bytes()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/octet-stream")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Upload error {e.code}: {e.read().decode(errors='replace')}")


# ── Steps ──────────────────────────────────────────────────────────────

def build_pyinstaller():
    run([sys.executable, "-m", "PyInstaller",
         "--name", "Treetime", "--windowed", "--onedir",
         f"--icon={ICON}", "-y", str(ROOT / "main.py")], cwd=ROOT)


def build_installer():
    if not ISCC.exists():
        sys.exit(f"Inno Setup not found at {ISCC}")
    run([str(ISCC), str(ISS)], cwd=ROOT)
    if not INSTALLER.exists():
        sys.exit("Installer not created — check Inno Setup output.")


def create_github_release(version: str, token: str):
    tag = f"v{version}"
    print(f"\nChecking for existing release {tag}...")

    # Delete existing release + tag if present (allows re-releasing same version)
    releases = gh_api("GET", f"/repos/{REPO}/releases", token)
    for r in releases:
        if r["tag_name"] == tag:
            print(f"Deleting existing release {r['id']}...")
            gh_api("DELETE", f"/repos/{REPO}/releases/{r['id']}", token)
            break

    # Delete tag ref if it exists
    try:
        gh_api("DELETE", f"/repos/{REPO}/git/refs/tags/{tag}", token)
    except SystemExit:
        pass  # tag didn't exist

    notes = (
        f"## Treetime {tag}\n\n"
        "**Install:** Download `TreetimeSetup.exe` below and run it.\n\n"
        "Your existing data is preserved on upgrade."
    )
    print(f"Creating release {tag}...")
    release = gh_api("POST", f"/repos/{REPO}/releases", token, body={
        "tag_name":         tag,
        "target_commitish": "main",
        "name":             f"Treetime {tag}",
        "body":             notes,
        "draft":            False,
        "prerelease":       False,
    })

    print(f"Uploading {INSTALLER.name} ({INSTALLER.stat().st_size // 1024 // 1024} MB)...")
    asset = upload_asset(release["upload_url"], token, INSTALLER)
    print(f"Asset uploaded: {asset['browser_download_url']}")
    return release["html_url"]


# ── Main ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    version = get_version()
    print(f"Building Treetime v{version}")
    token = get_token()

    build_pyinstaller()
    build_installer()
    url = create_github_release(version, token)

    print(f"\n{'='*60}")
    print(f"Released! Treetime v{version}")
    print(f"Download: {url}")
    print(f"{'='*60}")
