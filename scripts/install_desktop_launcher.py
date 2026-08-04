from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = repo_root()
    launcher = root / "scripts" / "energy-modeling"
    if not launcher.exists():
        print(f"Repo launcher not found: {launcher}", file=sys.stderr)
        return 1

    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        print(f"Desktop folder not found: {desktop}", file=sys.stderr)
        return 1

    target = desktop / "Energy Modeling.command"
    target.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {str(root)!r}",
                f"exec {str(launcher)!r}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    current = target.stat().st_mode
    target.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Created desktop launcher: {target}")
    print("Double-click it to start EDIM. Keep the Terminal window open while using the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
