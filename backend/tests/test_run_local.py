from pathlib import Path

from scripts import run_local


def test_local_runtime_config_uses_the_browser_origin(tmp_path: Path) -> None:
    run_local._write_frontend_runtime_config(tmp_path)

    content = (tmp_path / "runtime-config.local.js").read_text(encoding="utf-8")

    assert "window.EDIM_LOCAL_API_BASE = window.location.origin;" in content
    assert "127.0.0.1" not in content
