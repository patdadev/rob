from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_fake_python(tmp_path: Path) -> Path:
    fake_python = tmp_path / "fakepython"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'PYTHONPATH=%s\\n' \"${PYTHONPATH:-}\"\n"
        "printf 'ARGS=%s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    return fake_python


def test_rob_wrapper_resolves_real_repo_root_from_symlink(tmp_path: Path):
    fake_python = _write_fake_python(tmp_path)
    symlink_path = tmp_path / "rob"
    symlink_path.symlink_to(REPO_ROOT / "scripts" / "rob")

    env = os.environ.copy()
    env["PYTHON_BIN"] = str(fake_python)

    result = subprocess.run(
        [str(symlink_path), "queue", "status"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert f"PYTHONPATH={REPO_ROOT}" in result.stdout
    assert "ARGS=-m scripts.ops queue status" in result.stdout


def test_robctl_wrapper_resolves_real_repo_root_from_symlink(tmp_path: Path):
    fake_python = _write_fake_python(tmp_path)
    symlink_path = tmp_path / "robctl"
    symlink_path.symlink_to(REPO_ROOT / "scripts" / "robctl")

    env = os.environ.copy()
    env["PYTHON_BIN"] = str(fake_python)

    result = subprocess.run(
        [str(symlink_path), "queue", "status"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert f"PYTHONPATH={REPO_ROOT}" in result.stdout
    assert "ARGS=-m scripts.ops queue status" in result.stdout
