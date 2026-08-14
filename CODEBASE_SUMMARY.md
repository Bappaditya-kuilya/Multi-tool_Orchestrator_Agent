# Multi-Tool Orchestrator Agent - Codebase State Summary

**Date:** 2026-08-14
**Overall Rating:** 5.0/10 (from audit baseline)
**Tests:** 124 passed

---

## Project Overview

A Python 3.12 multi-tool orchestrator agent with pipeline: registry → router → permission → executor → orchestrator → auditor, plus message_queue for distributed mode. Tools are mock tools (weather, wikipedia, calculator, github-search). The project aims for 10/10 with zero critical findings, full packaging, documentation, and a free-LLM layer.

---

## What's DONE (Working Well)

### ✅ Core Functionality
- **124/124 tests pass** (`python3 -m pytest tests/ -q`)
- **Basic pipeline works**: task loading → routing → permission checking → execution → auditing
- **Mock tools functional**: calculator, weather, wikipedia, github-search, calculator-advanced
- **Registry loads YAML manifests** correctly, indexes by name and capability
- **Permission token issuance** based on tool scopes

### ✅ Infrastructure
- `pyproject.toml` configured with `pythonpath = ["."]` (fixes `.venv/bin/pytest` import error)
- `pydantic>=2.6,<3` and `PyYAML>=6.0,<7` dependencies installed
- MIT license included
- CLI has `run`, `list-tools`, `validate` subcommands

### ✅ Specific Features Working
- SafeEval handles `+`, `-`, `*`, `/`, `%`, `floor division`, unary ops
- Advanced calculator supports `sqrt`, `abs`, `round`, `min`, `max`
- Message queue has history cap (10,000) with ring buffer behavior
- AuditLog handles corrupt/empty lines gracefully
- Sanitize filename stem works for audit paths

---

## What's LEFT (Open Issues by Severity)

### 🔴 CRITICAL (Task 19 gate blocks on zero)

| ID | Issue | File(s) | Severity |
|----|-------|---------|----------|
| **C-1** | Sub-task privilege escape: child orchestrator out-scopes parent token | `orchestrator.py:95-103` — `_create_child_orchestrator` with empty `allowed_scopes` gives child ALL tools | CRITICAL |
| **C-2** | SafeEval `**` CPU-exhaustion: `9**9**9` burns 20s+ CPU | `mock_calculator.py:16,39` — unguarded `operator.pow` with massive exponents | CRITICAL |

### 🟠 HIGH (Must fix before 10/10)

| ID | Issue | File(s) | Current Rating |
|----|-------|---------|----------------|
| **H-1** | Unhandled `NoToolForCapability` crashes the whole run | `executor.py:98` (outside try), `router.py:42` raiser | 4/10 |
| **H-2** | Token inflation: poisoned manifest widens granted scopes | `permission.py:15-26` — unions `required_scope` over ALL routed tools | 3/10 |
| **H-3** | Reply-topic collision: cross-task reply interception & theft | `message_queue.py:94-115` — shared `reply.{task_id}` topic | 5/10 |
| **H-4** | Packaging gap + dead `ConflictResolver` | No `pythonpath` for fresh clones; `conflict.py` dead code never imported | 6/10 |

### 🟡 MEDIUM (Must fix for robustness)

| ID | Issue | File(s) | Current Rating |
|----|-------|---------|----------------|
| **CRASH-05** | CLI raw tracebacks on malformed task-file variants | `cli.py:32` (unguarded `from_task_file`), `orchestrator.py:51-55` | 6/10 |
| **CRASH-06** | MessageQueue unbounded memory + handler leak in `submit_and_wait` | `message_queue.py:30` (unbounded `_history`), handler leak no unsubscribe API | 5/10 |
| **CRASH-07** | SemanticMatcher quadratic `_substring_score` → CPU DoS | `semantic.py:91-94` — nested loops, 50M iterations for 5000×5000 | 5/10 |
| **CRASH-08** | Deep sub-task nesting: RecursionError swallowed as false success | `orchestrator.py:79-124` recursive child creation, `executor.py:141-156` catches RecursionError | 4/10 |

### 🟢 LOW (Hygiene/smells, should fix)

- `auditor.py:29` — `datetime.now(timezone.utc).isoformat()` warning (utcnow deprecation)
- `semantic.py:85-86` — empty query returns 0.5 (bug, fixed in similarity() at line 134)
- `message_queue.py:53` — ponytail comment: "ring buffer, swap to disk-backed if real traffic"
- Dead `AuditEntry` in `models.py` (QA-03), never used

---

## Subsystem Ranking (1-10, 1=worst, 10=best)

| Rank | Subsystem | Key Issues | Rating | Why |
|------|-----------|------------|--------|-----|
| 1 | **orchestrator.py** | C-1 privilege escape, C-8 recursion, C-13 empty sub-task silent success | **2/10** | Critical scope escalation; recursion depth exploit; silent success on empty sub-tasks |
| 2 | **permission.py** | H-2 token inflation — poisoned manifest grants ALL scopes | **3/10** | Single vulnerability: one evil manifest widens token to include admin scopes |
| 3 | **executor.py** | H-1 unhandled NoToolForCapability, CRASH-05/06/08 variants | **4/10** | Crash-on-any-failure; duplicate step-id overwrites; max_iterations dead |
| 4 | **message_queue.py** | H-3 reply collision, CRASH-06 memory leak | **5/10** | Topic collision enables reply theft; unbounded history → 700MB+ at 1M messages |
| 5 | **semantic.py** | CRASH-07 quadratic similarity, empty-query returns 0.5 | **5/10** | N×M substring scoring; empty query outranks everything |
| 6 | **cli.py** | CRASH-05 raw tracebacks, F-DX-6 exception handling | **6/10** | Full tracebacks on every error; missing exit code distinctions |
| 7 | **router.py** | QA-08 naive semantic fallback, empty-query 0.5 similarity | **6/10** | Falls back to 0.5 similarity for empty query; no real semantic index by default |
| 8 | **models.py** | QA-03 dead `AuditEntry`, model cleanup needed | **7/10** | `AuditEntry` class defined but never used; dead code |
| 9 | **registry.py** | Basic YAML loading, duplicate name check | **8/10** | Solid foundation; only raises on duplicates or missing dir |
| 10 | **tools/base.py + mock tools** | C-2 pow DoS, QA-32 GenericMockTool fallback | **6/10** | `9**9**9` DoS; GenericMockTool silently swallows unknown tool names |

---

## Free-LLM Layer Status (Phase 3.5, Tasks T20-T23)

**Not yet implemented.** Planned stdlib-only provider layer that would enable:

- **MockProvider** — offline default (zero API keys), returns canned plan JSON
- **OpenRouter `:free`** — free-tier router model `openrouter/free`
- **Gemini native** — `gemini-3.6-flash` with JSON mode
- **Groq** — `openai/gpt-oss-120b` for speed + strict JSON
- **build_provider/create_provider** — factory with env-driven defaults
- **chat_gemini_native / chat_openai_compat** — pure urllib.request builders/parsers

**Dependencies planned:** No new stdlib dependencies — all through `urllib.request` only.

---

## Key Decision Audit Trail (from plan.md)

Major rulings that shaped the codebase:

1. **Task 11**: Keep `create_tool` (live in both executors); update ALL resolver construction sites
2. **Task 14**: ParallelExecutor gets minimal O(n) scheduler (pending-deps counter + ready set)
3. **Task 19**: New Phase 3.5: stdlib-only LLM provider layer (urllib.request; NO openai/httpx SDK)
4. **Decision 8**: Token inflation fix (H-2) makes cross-scope fallback fail-closed by design
5. **Decision 19**: Delete `GenericMockTool` — fix test_integration's calc-high/calc-low manifests first!

---

## Execution Roadmap (Remaining Tasks)

Based on `plan.md` 24 tasks across 7 phases:

| Phase | Tasks | Focus |
|-------|-------|-------|
| **0** | T0-T7 | Security fixes: C-1 confinement, C-2 pow bound, H-1/2/3, CLI hardening |
| **1** | T8-10 | Correctness: semantic fixes, mock hardening, executor correctness |
| **2** | T11-14 | Wire or cut: executor unification, delete ConflictResolver, wire --semantic |
| **3** | T15-16 | Packaging: pyproject.toml, CI, LICENSE, README + docs |
| **3.5** | T20-23 | **NEW** Free-LLM layer: stdlib providers + NL planner + CLI `agent` subcommand |
| **4** | T17-18 | Test hygiene: tmp_path, gitignore, attack regression tests |
| **5** | T19 | **GATE** — zero warnings, attack probes fail closed, docs+demos run |

---

## Quick Fix Priorities (Ponytail: simplest first)

1. **Fix C-1** (`orchestrator.py:_create_child_orchestrator`): Pass parent token, deny when intersection empty, never prune to empty
2. **Fix C-2** (`mock_calculator.py:visit_BinOp`): Evaluate operands → bound-check → invoke pow; reject non-finite results
3. **Fix H-1** (`executor.py:_select_tools`): Wrap in try/except → failed ToolResult
4. **Fix H-2** (`permission.py:issue_token`): Grant only winner's scope per step (`tools[0].required_scope`)
5. **Fix H-3** (`message_queue.py`): Per-message reply topics (`reply.{message_id}`), correlation-id check, unsubscribe API
6. **Fix CLI** (`cli.py`): argparse rewrite; handlers print `Error: <message>`; exit codes 0/1/2
7. **Fix semantic empty query** (`semantic.py:134`): Already fixed — return 0.0 for empty query

---

## Build Status

- **Packaging:** `pip install -e .` works (created editable wheel)
- **Tests:** `python3 -m pytest tests/ -q` → 124 passed
- **CLI:** `python3 -m src.cli run tasks/demo-task.json` works from repo root
- **Not testable from fresh clone:** `.venv/bin/pytest` fails with `ModuleNotFoundError: No module named 'src'` until `pythonpath=["."]` is in pyproject.toml

---