"""Task 18 — consolidated attack-regression suite, keyed by docs/audit.md finding ID.

Every proven exploit in docs/audit.md must be pinned by a test.  Most fixes are
already regression-tested in other files (waves 1-4); those IDs are mapped below
with a comment, and only the MISSING coverage is written here (NEW tests at the
bottom).  This file never modifies existing tests.

Finding ID -> coverage map
==========================
C-1       sub-task privilege escape blocked
          -> tests/test_security_confinement.py::test_child_cannot_run_scope_parent_never_granted
C-2       SafeEval `**` CPU-exhaustion; `9**9**9` / `2**1_000_000` -> ValueError fast
          -> tests/test_security_pow.py::test_pow_exponent_bounded
          -> tests/test_tools.py::test_advanced_pow_bound_inherited
H-1       unhandled NoToolForCapability crashed the run
          -> tests/test_security_routing.py::test_executor_unknown_capability_returns_failed_result
          -> tests/test_security_routing.py::test_parallel_executor_unknown_capability_returns_failed_result
H-2       token inflation via poisoned manifest
          -> tests/test_security_tokens.py::test_token_not_inflated_by_poisoned_manifest
H-3       reply-topic collision / cross-task reply theft
          -> tests/test_security_queue.py::test_forged_reply_on_reply_topic_is_rejected
          -> tests/test_security_queue.py::test_concurrent_same_task_id_no_cross_delivery
H-4       packaging gap (no pyproject.toml -> "No module named 'src'")
          -> resolved by pyproject.toml (Task 15); every test here imports `src`
             and tests/test_cli.py::test_help_exits_0_and_lists_subcommands proves
             the CLI runs as `python -m src.cli` from a foreign cwd
CRASH-03  executor crash on unknown capability (alias of H-1) -> see H-1
CRASH-04  corrupt audit line tolerated
          -> tests/test_auditor.py::test_read_all_skips_corrupt_lines
CRASH-05  CLI raw tracebacks on malformed task files -> NEW below (E2-E5 variants;
          E1 missing file covered by tests/test_cli.py::test_missing_task_file_exits_2_with_friendly_error,
          E2 bad json by tests/test_cli.py::test_bad_json_task_file_exits_2_with_friendly_error)
CRASH-06  unbounded queue memory + handler leak
          -> tests/test_message_queue.py::test_history_capped_at_10000
          -> tests/test_message_queue.py::test_1000_submits_leave_no_stray_handlers
          -> tests/test_security_queue.py::test_no_handler_leak_after_reply
CRASH-07  SemanticMatcher quadratic _substring_score
          -> tests/test_semantic.py::test_rank_1000_word_query_50_docs_under_2s
CRASH-08  deep sub-task nesting: RecursionError swallowed as false success
          (depth cap -> clean failure) -> tests/test_security_depth.py::test_nested_sub_tasks_beyond_depth_limit_fail_cleanly
          (builds depth 55 > SUB_TASK_MAX_DEPTH=50; same cap the plan's depth-100 item pins)
CRASH-08/ duplicate step ids -> ValueError at parse time
CRASH-09  -> tests/test_executor.py::test_duplicate_step_ids_rejected
          -> tests/test_executor.py::test_duplicate_step_ids_rejected_parallel
CRASH-10  concurrent audit writers -> tolerant read_all as primary defense
          -> tests/test_auditor.py::test_read_all_skips_corrupt_lines
CRASH-11  1e308*10 / 1e1000 -> clean ValueError (safe_eval level)
          -> tests/test_tools.py::test_calculator_overflow_constant_fails
          -> tests/test_tools.py::test_calculator_mul_overflow_result_fails
          end-to-end "no invalid JSON on stdout" -> NEW below
CRASH-12  executor retains every result in memory -> design note only (Task 10
          documents the step-count cap / streaming as future); no regression test
VULN-05   queue auth: in-process trust boundary, labeled as such in code; reply
          integrity via correlation_id + unique topics pinned by H-3 tests above
VULN-06   CLI audit-path traversal
          -> tests/test_cli.py::test_audit_file_with_dotdot_rejected
          -> tests/test_cli.py::test_audit_file_absolute_outside_cwd_rejected
QA-08     similarity("", doc) == 0.0, not 0.5
          -> tests/test_semantic.py::test_empty_query_similarity_is_zero
QA-09     per_page="abc" -> no TypeError
          -> tests/test_tools.py::test_github_per_page_string_no_typeerror
          -> tests/test_tools.py::test_github_per_page_negative_clamped
          -> tests/test_tools.py::test_github_per_page_huge_clamped
QA-10     weather nondeterministic -> seeded deterministic
          -> tests/test_tools.py::test_weather_seeded_deterministic
QA-11     utcnow deprecation -> tz-aware UTC timestamps
          -> tests/test_auditor.py::test_timestamps_tz_aware_utc
QA-12     child audit filename path traversal sanitized
          -> tests/test_auditor.py::test_child_audit_filename_sanitized
QA-13     empty sub_task -> explicit failure, not silent success
          -> tests/test_security_depth.py::test_empty_sub_task_steps_fail
QA-14     get_results returns None for unknown task
          -> tests/test_message_queue.py::test_get_results_unknown_task_is_none
QA-19     --help lists --parallel/--semantic flags
          -> tests/test_cli.py::test_help_lists_parallel_and_semantic_flags
QA-22     benchmark speedup flakiness
          -> tests/test_benchmark.py::test_parallel_speedup
QA-32     create_tool unknown name -> loud ValueError, no silent GenericMockTool
          -> tests/test_tools.py::test_unknown_tool_name_raises_value_error
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = REPO_ROOT / "manifests"


def _run_cli(tmp_path, task_file, *args):
    """Subprocess CLI runner: sys.executable, cwd=tmp_path (CRASH-05 constraint)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "src.cli", "run", str(task_file), str(MANIFESTS), *map(str, args)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _write_task(tmp_path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


# CRASH-05: every malformed task-file variant must exit with a friendly
# "Error: ..." message and never print a Python traceback.  E2 (bad json) and
# E1 (missing file) are covered in test_cli.py; E2-E5 pinned here so the whole
# proof of CRASH-05 lives in the finding-keyed suite.
@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("bad-json.json", "{not valid json"),                                          # E2
        ("no-task-id.json", json.dumps({"steps": []})),                                # E3
        ("steps-not-list.json", json.dumps({"task_id": "t", "steps": "notalist"})),    # E4
        ("no-capability.json", json.dumps({"task_id": "t", "steps": [{"id": "s1"}]})),  # E5
    ],
    ids=["bad-json", "no-task-id", "steps-not-list", "no-capability"],
)
def test_crash05_cli_malformed_task_file_no_traceback(tmp_path, name, content):
    task_file = _write_task(tmp_path, name, content)
    r = _run_cli(tmp_path, task_file)
    assert r.returncode == 2
    assert r.stderr.strip().startswith("Error:")
    assert "Traceback" not in r.stderr
    assert "Traceback" not in r.stdout


# CRASH-11 end-to-end: an overflowing expression must surface as a clean
# failure — the CLI must never emit invalid JSON (json.dumps would emit
# `Infinity`).  The safe_eval-level ValueError is pinned in test_tools.py;
# this test pins "nothing invalid JSON" at the process boundary.
def test_crash11_cli_overflow_never_emits_invalid_json(tmp_path):
    task_file = _write_task(
        tmp_path,
        "overflow.json",
        json.dumps({
            "task_id": "overflow",
            "steps": [
                {"id": "s1", "capability": "calculator", "input": {"expression": "1e308*10"}},
            ],
        }),
    )
    r = _run_cli(tmp_path, task_file)
    assert "Traceback" not in r.stderr
    assert "Traceback" not in r.stdout
    assert "Infinity" not in r.stdout and "NaN" not in r.stdout
    out = json.loads(r.stdout.split("Audit log written")[0])
    assert out["results"]["s1"]["success"] is False
    assert "range" in out["results"]["s1"]["error"]
