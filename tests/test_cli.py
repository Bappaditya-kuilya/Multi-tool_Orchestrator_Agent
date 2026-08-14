from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = REPO_ROOT / "manifests"


def run_cli(tmp_path, *args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *map(str, args)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def _write_task(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_bad_json_task_file_exits_2_with_friendly_error(tmp_path):
    bad = _write_task(tmp_path, "bad.json", "{not valid json")
    r = run_cli(tmp_path, "run", bad, MANIFESTS)
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Error:")
    assert "Traceback" not in r.stderr


def test_missing_task_file_exits_2_with_friendly_error(tmp_path):
    r = run_cli(tmp_path, "run", tmp_path / "missing.json", MANIFESTS)
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Error:")
    assert "Traceback" not in r.stderr


def test_help_exits_0_and_lists_subcommands(tmp_path):
    r = run_cli(tmp_path, "--help")
    assert r.returncode == 0
    for sub in ("run", "list-tools", "validate"):
        assert sub in r.stdout


def test_help_lists_parallel_and_semantic_flags(tmp_path):
    r = run_cli(tmp_path, "run", "--help")
    assert r.returncode == 0
    assert "--parallel" in r.stdout
    assert "--semantic" in r.stdout


def test_unknown_flag_exits_1_usage_error(tmp_path):
    r = run_cli(tmp_path, "run", "--nope", "task.json", MANIFESTS)
    assert r.returncode == 1
    assert "error" in r.stderr.lower()
    assert "Traceback" not in r.stderr


def test_audit_file_with_dotdot_rejected(tmp_path):
    task = _write_task(tmp_path, "ok.json", {"task_id": "t", "steps": []})
    r = run_cli(tmp_path, "run", task, MANIFESTS, "--audit-file", "../escape.json")
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Error:")
    assert "Traceback" not in r.stderr


def test_audit_file_absolute_outside_cwd_rejected(tmp_path):
    task = _write_task(tmp_path, "ok.json", {"task_id": "t", "steps": []})
    outside = tmp_path.parent / "escape.json"
    r = run_cli(tmp_path, "run", task, MANIFESTS, "--audit-file", str(outside))
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Error:")
    assert "Traceback" not in r.stderr
