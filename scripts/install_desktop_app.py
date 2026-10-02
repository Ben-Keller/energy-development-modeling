from __future__ import annotations

import plistlib
import shutil
import stat
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = repo_root()
    runner = root / "scripts" / "run_local.py"
    python_bin = root / "backend" / ".venv" / "bin" / "python"
    loading_page = root / "scripts" / "desktop_loading.html"
    if not runner.exists():
        print(f"Local runner not found: {runner}", file=sys.stderr)
        return 1
    if not python_bin.exists():
        print(f"Python environment not found: {python_bin}", file=sys.stderr)
        return 1
    if not loading_page.exists():
        print(f"Desktop loading page not found: {loading_page}", file=sys.stderr)
        return 1

    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        print(f"Desktop folder not found: {desktop}", file=sys.stderr)
        return 1

    app = desktop / "Energy Modeling.app"
    if app.exists():
        shutil.rmtree(app)

    macos_dir = app / "Contents" / "MacOS"
    resources_dir = app / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

    executable_name = "Energy Modeling"
    executable = macos_dir / executable_name
    executable.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"REPO_ROOT={str(root)!r}",
                'PYTHON_BIN="${REPO_ROOT}/backend/.venv/bin/python"',
                'RUNNER="${REPO_ROOT}/scripts/run_local.py"',
                'LOADING_PAGE="${REPO_ROOT}/scripts/desktop_loading.html"',
                'OUTPUT_DIR="${REPO_ROOT}/outputs"',
                'PID_FILE="${OUTPUT_DIR}/local_app.pid"',
                'URL_FILE="${OUTPUT_DIR}/local_app.url"',
                'LOG_FILE="${OUTPUT_DIR}/desktop-launcher.log"',
                'mkdir -p "${OUTPUT_DIR}"',
                'export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"',
                'if [[ -f "${URL_FILE}" ]]; then',
                '  URL="$(cat "${URL_FILE}" 2>/dev/null || true)"',
                '  if [[ -n "${URL}" ]] && /usr/bin/curl -fsS --max-time 1 "${URL}" >/dev/null 2>&1; then',
                '    open "${URL}" || true',
                '    exit 0',
                '  fi',
                'fi',
                'if [[ -f "${PID_FILE}" && -f "${URL_FILE}" ]]; then',
                '  PID="$(cat "${PID_FILE}" 2>/dev/null || true)"',
                '  URL="$(cat "${URL_FILE}" 2>/dev/null || true)"',
                '  if [[ "${PID}" =~ ^[0-9]+$ ]] && kill -0 "${PID}" 2>/dev/null; then',
                '    open "${URL:-http://127.0.0.1:8000/ui/}" || true',
                '    exit 0',
                '  fi',
                'fi',
                'cd "${REPO_ROOT}"',
                'open "${LOADING_PAGE}" || true',
                'nohup "${PYTHON_BIN}" "${RUNNER}" >> "${LOG_FILE}" 2>&1 &',
                "exit 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    plist = {
        "CFBundleDisplayName": "Energy Modeling",
        "CFBundleExecutable": executable_name,
        "CFBundleIdentifier": "org.undp.edim.local-launcher",
        "CFBundleName": "Energy Modeling",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSBackgroundOnly": True,
        "LSMinimumSystemVersion": "10.15",
    }
    with (app / "Contents" / "Info.plist").open("wb") as fh:
        plistlib.dump(plist, fh)

    print(f"Created desktop app launcher: {app}")
    print("Double-click the app to start EDIM without a Terminal prompt.")
    print(f"Logs are written to: {root / 'outputs' / 'desktop-launcher.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
