# 10/10 Rebuild Plan — Multi-Tool Orchestrator Agent (Ponytail-Refined)

**Goal:** Take the audited Multi-Tool Orchestrator Agent (5.0/10) to 10/10: zero critical/high security findings, zero crash paths, no dead code, packaged, documented, fully tested — plus a free-LLM layer so the agent runs at $0 on Groq / Gemini / OpenRouter (NL request → plan → execute), with an offline mock mode needing no keys.

**Target Audience:** Backend engineer evaluating permission-scoped tool delegation patterns
**Success Criterion:** Read architecture doc, run demos, extend with one new tool manifest + class in < 15 min, find no code path that crashes or escalates scopes.

---

## Ponytail Refinements Applied

| Original | Refined | Reason |
|----------|---------|--------|
| T20-T23: 4 files for free-LLM | T20: 1 file `src/llm.py` (MockProvider + providers + planner) | Merge into single module; defer CLI agent + doc until after gate |
| T12: Custom O(n) scheduler | T12: Use `asyncio.as_completed` with dependency tracking | Stdlib over custom code |
| T5: 3 features in one task | T5a: reply.{message_id} only; T5b: unsubscribe only if needed | Split; YAGNI |
| T2: Complex bit_length bound | T2: Simple exponent cap `right > 1000` | Ponytail: simplest fix that works |
| T16: 3 doc files | T16: 1 `README.md` with architecture + free-LLM section | Combine |

---

## Phase 0: Documentation & Traceability (T0)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T0 | Create `docs/audit.md` consolidating every finding with evidence (traceability key for regression tests) | `docs/audit.md` (new) | `grep -r "C-1\|C-2\|H-1\|H-2\|H-3\|CRASH-" docs/audit.md` finds all 10+ IDs |

---

## Phase 1: Security Fixes (T1-T7) — CRITICAL/HIGH

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T1 | **C-1 Sub-task confinement**: Pass parent token to `run_sub_task(sub_task, parent_token)`. Deny at token layer when intersection empty. Never prune child registry to empty. | `orchestrator.py:95-103` (`_create_child_orchestrator`), `orchestrator.py:112-115` (`run_sub_task`), `executor.py:103-111` (`_run_sub_task`) | `tests/test_attacks.py::test_subtask_no_privilege_escape` passes |
| T2 | **C-2 SafeEval pow bound**: In `visit_BinOp` for `ast.Pow`: evaluate operands → bound-check `right > 1000` → invoke `operator.pow`. Reject non-finite results. | `mock_calculator.py:39-54` (`visit_BinOp`), `mock_calculator_advanced.py` (inherits) | `tests/test_attacks.py::test_pow_cpu_dos` passes (< 1s) |
| T3 | **H-1 NoToolForCapability graceful failure**: Wrap `_select_tools` in try/except → return failed `ToolResult("No tool for capability: X")`. Same in both executors. | `executor.py:87-88` (`_select_tools`), `executor.py:235` (ParallelExecutor `_run_step`) | `tests/test_attacks.py::test_no_tool_graceful` passes |
| T4 | **H-2 Token inflation fix**: Grant only winner's scope per step (`tools[0].required_scope`). Cross-scope fallback becomes fail-closed by design. | `permission.py:15-26` (`issue_token`), `executor.py:91` (`_check_permission`) | `tests/test_attacks.py::test_token_inflation_denied` passes |
| T5a | **H-3 Reply-topic collision fix (core)**: Per-message reply topics (`reply.{message_id}`), correlation-id check. | `message_queue.py:94-115` (`DistributedExecutor._new_request`, `submit_and_wait`) | `tests/test_attacks.py::test_reply_collision_denied` passes |
| T5b | **H-3 Unsubscribe API** (only if T5a tests reveal handler leak) | `message_queue.py:44-47` (add `unsubscribe` used in `finally`) | `tests/test_message_queue.py::test_handler_leak_fixed` passes |
| T6 | **CLI hardening**: argparse rewrite; handlers print `Error: <message>`; exit codes 0/1/2; catch `Exception` only (re-raise KeyboardInterrupt/SystemExit/BrokenPipeError). | `cli.py:17-119` (entire CLI) | `tests/test_cli.py` all pass; `tests/test_attacks.py::test_cli_no_raw_tracebacks` passes |
| T7 | **Audit resilience**: Fix utcnow deprecation warning at `auditor.py:29` → `datetime.now(timezone.utc)`. Corrupt-line handling already works. | `auditor.py:29` | `pytest tests/ -q` → zero warnings |

---

## Phase 2: Correctness Fixes (T8-T10)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T8 | **Semantic fixes**: Empty query returns 0.0 (already at `semantic.py:134`). Add "temp" → SYNONYM_MAP for weather routing. Prefix buckets for quadratic `_substring_score`. | `semantic.py:9-18` (SYNONYM_MAP), `semantic.py:109-120` (`_substring_score`), `semantic.py:132-135` (`similarity`) | `tests/test_attacks.py::test_semantic_empty_query_zero` passes; `tests/test_semantic.py` all pass |
| T9 | **Mock tool hardening**: Weather deterministic with seed. Calculator advanced: allowlist adds `ast.Call`+`ast.Name` (F-6). Pow bound check order: operands → bound-check → invoke. | `mock_weather.py:20-28` (deterministic seed), `mock_calculator_advanced.py:11-42` (`AdvancedSafeEval`) | `tests/test_tools.py` all pass; `tests/test_attacks.py::test_mock_tool_hardening` passes |
| T10 | **Executor correctness**: Duplicate step-ids raise ValueError (already at `executor.py:19-24`). Empty sub-task → fail, not silent success. Depth cap via `contextvars.ContextVar` (already at `orchestrator.py:26`). | `executor.py:19-24` (`_validate_unique_step_ids`), `orchestrator.py:79-124` (child orchestrator), `orchestrator.py:26` (`SUB_TASK_MAX_DEPTH`) | `tests/test_executor.py` all pass; `tests/test_attacks.py::test_duplicate_step_id_rejected` passes |

---

## Phase 3: Wire or Cut (T11-T14)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T11 | **Delete ConflictResolver**: Remove `src/conflict.py` entirely. Update ALL construction sites. Keep `create_tool` (live in both executors). | `src/conflict.py` (delete), `orchestrator.py:79-93`, `orchestrator.py:45-76`, `orchestrator.py:79-93`, `executor.py`, `cli.py` | `grep -r "ConflictResolver" src/` → zero matches; `pytest tests/` all pass |
| T12 | **Executor unification + wire `--parallel`**: Single execution core shared by `Executor` and `ParallelExecutor`. Wire `--parallel` flag through `from_task_file` and `create`. ParallelExecutor uses `asyncio.as_completed` with pending-deps counter (minimal, ~15 lines). | `executor.py:27-230` (Executor), `executor.py:230+` (ParallelExecutor), `orchestrator.py:45-76` (`from_task_file`), `orchestrator.py:79-93` (`create`), `cli.py:72` | `tests/test_executor.py::test_parallel_scheduler` passes; `python3 -m src.cli run --parallel examples/demo-task.json` works |
| T13 | **Wire `--semantic` flag**: Router `use_semantic` enabled via CLI flag. Semantic index built on demand. | `router.py:21-27` (`__init__`, `_build_semantic_index`), `cli.py:58` (`--semantic` flag) | `python3 -m src.cli run --semantic examples/demo-task.json` works |
| T14 | **DistributedExecutor honest + delete GenericMockTool**: Per-message reply topics (T5a), history cap, tz timestamps. Delete `GenericMockTool` — fix `test_integration.py` calc-high/calc-low manifests first! | `message_queue.py:27-104` (`MessageQueue`), `message_queue.py:106+` (`DistributedExecutor`), `tests/test_integration.py` manifests | `tests/test_message_queue.py` all pass; `tests/test_integration.py` all pass |

---

## Phase 4: Packaging & Docs (T15-T16)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T15 | **Packaging**: `pyproject.toml` with `pythonpath = ["."]` (already), CI (GitHub Actions: pytest + compileall), MIT LICENSE (already). | `.github/workflows/ci.yml` (new), `pyproject.toml`, `LICENSE` | `python3 -m pytest tests/ -q` passes in fresh clone; `compileall -q src/` zero errors |
| T16 | **Docs & Demos**: Single `README.md` with architecture, quickstart, exit codes, "Adding a tool" section (manifest schema + TOOL_CLASSES + test pointer), free-tier reference. Examples run from repo root. | `README.md` (new), `examples/demo-task.json` | Fresh clone: `pip install -e . && python3 -m src.cli run examples/demo-task.json` works |

---

## Phase 4.5: Free-LLM Layer (T20) — DEFERRED (Post-Gate)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T20 | **stdlib-only LLM provider layer**: `src/llm.py` with `MockProvider`, `Provider`, `create_provider`, `build_openai_compat_request`, `parse_openai_compat_response`, `chat_openai_compat`, `build_gemini_request`, `parse_gemini_response`, `chat_gemini_native`, `retry_with_backoff`, `plan_from_nl` (NL planner). Pure urllib.request. | `src/llm.py` (new), `src/llm/__init__.py` (export) | `tests/test_llm.py` unit tests pass (request builders/parsers only, no network) |
| T21 | **CLI `agent` subcommand** (deferred) | `cli.py` (add `agent` subparser) | `python3 -m src.cli agent "test" --provider mock` works |
| T22 | **Free-tier reference doc** (deferred) | `README.md` (add section) | Section renders |

> **Note:** Phase 4.5 is deferred to post-gate iteration. The gate (T19) only requires core 10/10 without LLM layer. Free-LLM is a "nice-to-have" stretch goal.

---

## Phase 5: Test Hygiene & Attack Regression (T17-T18)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T17 | **Test hygiene**: Move stray audit files to `tmp_path`. Gitignore strays. Stable benchmarks. CWD-independent `test_integration.py` manifests. CLI subprocess tests use `sys.executable` + arg lists. | `tests/conftest.py` (tmp_path fixture), `.gitignore`, `tests/test_integration.py`, `tests/test_cli.py` | `pytest tests/ -q` passes from any CWD; no stray files at repo root |
| T18 | **Attack regression suite**: `tests/test_attacks.py` — every exploit from `docs/audit.md` as a regression test, keyed by finding ID (C-1, C-2, H-1, H-2, H-3, CRASH-05, CRASH-06, CRASH-07, CRASH-08). | `tests/test_attacks.py` (new/expanded) | `pytest tests/test_attacks.py -q` → all pass; each test maps to finding ID |

---

## Phase 6: Final Gate (T19)

| Task | Description | Verification |
|------|-------------|--------------|
| T19 | **Final gate**: Zero warnings, attack probes fail closed, docs+demos run, no stdlib-violating imports, audit traceability table, final rating table (target 9+/10). | 1. `pytest tests/ -q` → 0 warnings<br>2. `pytest tests/test_attacks.py -q` → all pass<br>3. `python3 -m src.cli run examples/demo-task.json` works<br>4. `grep -r "import openai\|import httpx" src/` → zero matches<br>5. `docs/audit.md` traceability table complete<br>6. Final rating table in `docs/audit.md` shows 9+/10 |

---

## Task Dependency Graph

```
T0
  ├─
T1, T2, T3, T4, T5a, T6, T7 (parallel — security fixes)
  ├─
T5b (conditional — only if T5a reveals leak)
  ├─
T8, T9, T10 (parallel — correctness)
  ├─
T11, T12, T13, T14 (parallel — wire/cut)
  ├─
T15, T16 (parallel — packaging/docs)
  ├─
T17, T18 (parallel — test hygiene + attack regressions)
  ├─
T19 (final gate)
  ├─ (post-gate)
T20, T21, T22 (free-LLM stretch)
```

---

## Anti-Pattern Guards (Ponytail)

| Anti-Pattern | Guard |
|--------------|-------|
| New dependency for stdlib task | Use `urllib.request`, `json`, `dataclasses`, `contextvars` only |
| Speculative abstraction | No interface with one implementation; no factory for one product |
| Boilerplate "for later" | Delete `GenericMockTool` (T14), delete `ConflictResolver` (T11) |
| Custom cache class | `@lru_cache` or nothing until profiler says otherwise |
| Complex retry logic | `retry_with_backoff` with 3 attempts, exponential backoff — 15 lines max |
| Framework for tests | `assert`-based self-checks or one small `test_*.py` per module |

---

## Phase Verification Checklists

**Phase 1 (Security):**
- [ ] `pytest tests/test_attacks.py -xvs -k "subtask or pow or no_tool or token_inflation or reply_collision or cli_no_raw"` passes
- [ ] `pytest tests/ -q` → zero warnings

**Phase 2 (Correctness):**
- [ ] `pytest tests/test_attacks.py::test_semantic_empty_query_zero -xvs` passes
- [ ] `pytest tests/test_tools.py -xvs` passes
- [ ] `pytest tests/test_executor.py::test_duplicate_step_id_rejected -xvs` passes
- [ ] `pytest tests/test_integration.py -xvs` passes

**Phase 3 (Wire/Cut):**
- [ ] `grep -r "ConflictResolver" src/` → zero matches
- [ ] `python3 -m src.cli run --parallel examples/demo-task.json` works
- [ ] `python3 -m src.cli run --semantic examples/demo-task.json` works
- [ ] `pytest tests/test_message_queue.py -xvs` passes

**Phase 4 (Packaging):**
- [ ] Fresh clone: `pip install -e . && python3 -m pytest tests/ -q` passes
- [ ] `compileall -q src/` zero errors
- [ ] `python3 -m src.cli run examples/demo-task.json` works from any CWD

**Phase 5 (Tests):**
- [ ] `pytest tests/ -q` passes from any CWD
- [ ] `pytest tests/test_attacks.py -q` all pass, each maps to finding ID

**Phase 6 (Gate):**
- [ ] All above checks pass
- [ ] Final rating table in `docs/audit.md` shows 9+/10

---

## Estimated Effort (Refined)

| Phase | Tasks | Est. Lines Changed | Risk |
|-------|-------|-------------------|------|
| 0 | 1 | ~100 (docs) | Low |
| 1 | 7 (+1 conditional) | ~150 (security-critical) | High — must get right |
| 2 | 3 | ~100 | Medium |
| 3 | 4 | ~120 | Medium |
| 4 | 2 | ~80 (CI + docs) | Low |
| 4.5 | 1 (deferred) | ~200 (new LLM layer) | Medium — deferred |
| 5 | 2 | ~150 (tests) | Medium |
| 6 | 1 | ~50 (verification) | Low |

**Total (core):** ~750 lines changed across ~25 tasks. Expected 1-2 days with parallel subagents.

---

## Success Metrics (10/10 Definition)

| Dimension | 5/10 (Current) | 10/10 (Target) |
|-----------|----------------|----------------|
| Security | 2/10 (C-1, C-2, H-2, H-3) | 10/10 (zero CRITICAL/HIGH) |
| Crash-safety | 3/10 (5 crash paths) | 10/10 (zero crash paths) |
| YAGNI | 3/10 (dead code, over-engineered) | 10/10 (no dead code, minimal) |
| DX | 3/10 (raw tracebacks, no exit codes) | 10/10 (clean errors, docs, 15-min extend) |
| Free-LLM | 0/10 (not implemented) | 5/10 (deferred stretch; MockProvider works) |
| Tests | 41 passing, 35 warnings | 124+ passing, 0 warnings |
| Packaging | Not installable fresh | Installable, CI green |
| **Overall** | **5.0/10** | **9.5+/10** |

---

## Quick Start for Phase 1 (Ponytail Style)

```bash
# T1: Pass parent token, deny empty intersection
# Edit orchestrator.py:95-115, executor.py:103-111

# T2: Simple exponent cap right > 1000
# Edit mock_calculator.py:39-54

# T3: Wrap _select_tools in try/except
# Edit executor.py:87-88, 235

# T4: Grant only tools[0].required_scope
# Edit permission.py:15-26

# T5a: reply.{message_id}, correlation_id
# Edit message_queue.py:94-115

# T6: argparse rewrite, exit codes, Exception-only catch
# Edit cli.py:17-119

# T7: datetime.now(timezone.utc)
# Edit auditor.py:29

# Verify
pytest tests/test_attacks.py -xvs -k "subtask or pow or no_tool or token_inflation or reply_collision or cli_no_raw"
pytest tests/ -q  # zero warnings
```

---

*Plan complete. Ponytail-refined: ~25 core tasks, free-LLM deferred. Ready for execution.*