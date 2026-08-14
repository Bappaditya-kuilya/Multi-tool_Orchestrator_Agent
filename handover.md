# Handover — Multi-Tool Orchestrator Agent

> **Read this first.** This document is the complete knowledge transfer: what exists, what is being built, every decision ever made, the verified free-LLM landscape, and exactly how to run/verify/build this project. Written 2026-08-13. Status: **planning complete, build NOT yet started (awaiting final approval gate).**

---

## 1. TL;DR status

| Item | State |
|---|---|
| Project | Python 3.12 multi-tool orchestrator agent (registry → router → permission → executor → orchestrator → auditor, + message_queue for distributed mode) |
| Audit (3-agent, 2 hackers + code-quality) | Done → **5.0/10** overall: Security 2, Crash-safety 3, YAGNI 3, DX 3 (out of 10) |
| Baselines | `41 tests pass` (`python -m pytest tests/ -q`), 35 warnings (all `utcnow` in `src/auditor.py:29`); `.venv/bin/pytest` FAILS (`ModuleNotFoundError: No module named 'src'` — packaging gap) |
| Plan | `plan.md` — 24 tasks / 7 phases (incl. new free-LLM phase), decision audit trail with 21 rows |
| Reviews | CEO review applied; Eng review (11 findings F-1..F-11) applied; DX review pending; **final approval gate not yet run** |
| Build | **NOT started.** Do not build before the gate is approved (user's explicit "plan first then build"). |
| New scope (2026-08-13) | Free-LLM layer: run the agent at $0 on Groq / Gemini / OpenRouter / mocks — named user wants zero-cost LLM providers |
| Handover artifacts | `plan.md` (the plan), this file, restore point at `/tmp/opencode/plan-restore-*.md` |

---

## 2. What this project is

A learning-oriented, permission-scoped multi-tool orchestration agent. A **task** (JSON) is a list of **steps** where each step names a *capability* (e.g. `calculator`, `github-search`); a router maps capability → tool (from YAML manifests), a permission system grants scopes, and executors run steps sequentially or in parallel (with dependency scheduling), falling back across tools for the same scope. Tools are **mock tools** (weather, wikipedia, calculator/reverse-polish, github-search). A distributed mode runs via an in-process message queue.

Audience (CEO-review decision, locked): a backend engineer evaluating scoped tool-delegation patterns. Success criterion: reads the architecture doc, runs demos, extends with one new tool manifest + class in < 15 min, finds no code path that crashes or escalates scopes.

---

## 3. What EXISTS right now (as of this handover)

### Source modules (`src/`)
| Module | Purpose | Known problems (from audit) |
|---|---|---|
| `src/registry.py` | ToolRegistry: loads YAML manifests, sorts by priority | — |
| `src/router.py` | Router: capability → tool; semantic fallback | `_semantic_route` naive; empty-query `0.5` similarity (QA-08) |
| `src/permission.py` | PermissionScoper: `issue_token` | **H-2 token inflation** (UNION of scopes over ALL routed tools — a poisoned manifest inflates grants) |
| `src/executor.py` | Executor + ParallelExecutor | ~90 duplicated lines (QA-04); `_select_tools` raises unhandled `NoToolForCapability` (H-1, line 98); recursion for sub-tasks (CRASH-08); duplicate step-ids overwrite silently (CRASH-09); max_iterations dead (QA-05) |
| `src/orchestrator.py` | Orchestrator, `from_task_file`, child orchestrator creation | **C-1 sub-task privilege escape** (`_create_child_orchestrator` ~line 79: empty `allowed_scopes` → child gets ALL tools); child audit filename path traversal (QA-12); empty sub-task silent success (QA-13) |
| `src/auditor.py` | AuditEntry, AuditLog JSONL | `utcnow` warning (line 29); corrupt-line crashes (`read_all` lines 44-51) (CRASH-04) |
| `src/message_queue.py` | Message, MessageQueue, DistributedExecutor | **H-3/CRASH-02 reply spoof + topic collision** (`reply.{task_id}` shared; lines 99/105-108); handler leak (CRASH-06); `get_results` None (QA-14); naive timestamps |
| `src/semantic.py` | naive token-overlap similarity | quadratic (VULN-08); empty query returns 0.5 (QA-08) |
| `src/conflict.py` | ConflictResolver | **dead code** — never called (QA-01/27); slated for deletion (Task 11) |
| `src/cli.py` | CLI (currently `--task-file` only) | raw tracebacks, `--help` unknown, `--parallel`/`--semantic` flags exist but are not wired (QA-19, VULN-06); no exit codes |
| `src/tools/base.py` + `mock_{calculator,weather,wikipedia,github}.py` | mock tools | `9**9**9` CPU DoS (C-2, mock_calculator.py:16/39); weather nondeterministic; per_page TypeError; `GenericMockTool` silently swallows unknown tool names (QA-32) |
| `src/models.py` | pydantic models (Task, Step, ToolManifest, audit) | dead `AuditEntry` (QA-03) |

### Tests (`tests/`) — 13 files, 41 tests, all green (with `python -m pytest`)
`test_auditor, test_benchmark, test_conflict, test_executor, test_fallback, test_integration, test_message_queue, test_multiagent, test_permission, test_router, test_semantic, test_tools`. Also `test_fallback_audit.jsonl`, `test_par_audit.jsonl`, `test_seq_audit.jsonl` **stray at repo root** (must move to tmp_path, Task 17).

### Manifests & examples
`manifests/*.yaml` (calculator incl. advanced, weather, wikipedia, github-search), `examples/demo-task.json`.

### Verified probe results (reference — the audit's live proofs)
- **Cross-scope fallback works today:** with failing `calculator:eval` (priority 10) + poisoned `admin:eval` (priority 5), step falls back → `1024.0`. This *works* because the scope check is per-tool at executor.py:102; it is NOT protected against the inflation test (H-2) — the two interact, see Decision 8.
- **Poisoned manifest inflation:** one evil manifest inflates the token's granted scopes (H-2).
- `similarity("temp", weather-doc) == 0.0` (F-4: the CLI semantic demo does not route `temp` today).

---

## 4. THE PLAN — what will be built (24 tasks, 7 phases)

Living doc: **`plan.md`** (same directory). Phases run in order; tasks within a phase run as parallel subagents. Checkbox syntax per task. **Read plan.md before building anything.**

| Phase | Tasks | What |
|---|---|---|
| 0 | T0 | `docs/audit.md`: consolidate every finding with evidence (traceability key for T18) |
| 0 (Security) | T1-7 | C-1 subtask confinement (token passed to child), C-2 pow bound, H-1 no-tool graceful failure, H-2 token inflation (winner-only), H-3 queue auth/reply integrity, CLI hardening (argparse, exit codes), audit resilience (corrupt lines, tz-aware, sanitized filenames) |
| 1 (Correctness) | T8-10 | semantic fixes, mock-tool hardening + advanced calculator, executor correctness (dup ids, empty subtasks, depth cap via ContextVar, per_page clamping) |
| 2 (Wire or cut) | T11-14 | executor unification + delete ConflictResolver (update ALL construction sites, keep `create_tool`), wire `--semantic`, DistributedExecutor honest (per-message reply topics, unsubscribe, history cap, tz timestamps), delete `GenericMockTool` (fix test_integration's calc-high/calc-low manifests first!) |
| 3 (Packaging) | T15-16 | pyproject.toml (+ `pythonpath=["."]` fixes `.venv/bin/pytest`!), CI (GitHub Actions), MIT LICENSE; README + docs/architecture.md + demos |
| 3.5 (**NEW — free-LLM**) | T20-23 | stdlib-only provider layer (`src/llm/`) with OpenRouter/Groq/Gemini/Mock; NL planner (NL request → Task JSON); CLI `agent` subcommand (NL→plan→execute, `--provider auto`); `docs/free-llm.md` free-tier reference |
| 4 (Tests) | T17-18 | test hygiene (tmp_path, gitignore strays, stable benchmarks); `tests/test_attacks.py` — every exploit from docs/audit.md as a regression (findings-keyed) |
| 5 (Gate) | T19 | final gate: zero warnings, attack probes fail closed, docs+demos run, no stdlib-violating imports, audit traceability table, final rating table (target 9+/10) |

**Execution order details:** T0 before tests encoding findings; T5 before T13; T9 before T14; Phase 3.5 after Phase 3, before Phase 4; T19 last.

---

## 5. EVERY DECISION (must know before touching the code)

Full table lives in `plan.md` (21 rows). Summary of the load-bearing ones:

**User-level, locked:**
1. **Wire-or-cut policy:** every subsystem reachable via CLI or deleted. No dead code (this is what kills `ConflictResolver`, `AuditEntry`, `GenericMockTool`).
2. **Mock tools stay mock** — harden, don't swap to live APIs.
3. **No new dependencies** — stdlib first; Python 3.12; `ponytail:` comments mark deliberate simplifications with upgrade paths.
4. **Tests write only to `tmp_path`** — never repo root.
5. **Ponytail skill mandatory in every task** (user standing instruction: laziest working solution).
6. **Plan first, then build** — build does not start until the final gate is approved.
7. **Free-first LLM providers** (2026-08-13): the agent must be drivable by Groq / Gemini / OpenRouter free tiers — $0 budget, offline mock mode with zero keys.

**Review-driven (from autoplan CEO + Eng reviews):**
8. **Token inflation fix = winner-only grant** (`tools[0].required_scope` per step). NOT union-per-step (reopens H-2). Consequence: cross-scope fallback becomes **fail-closed by design** — fallback only among tools whose scope is already granted; must be regression-tested (T18: "cross-scope fallback denial"). Do not "fix" this back.
9. **Task 1 signature change**: `run_sub_task(sub, parent_token)` — flip the test at Step 3, not Step 1; empty intersection denies at the token layer only (never prune registry to empty — that trips the ordering of NoToolForCapability handling); update BOTH executor call sites (line 96 AND line 220) + `test_multiagent.py:55,67`.
10. **Task 4's test needs a legit winner**: manifests dir must include BOTH a legit calculator tool (priority 200; the winner) AND the evil poisoned one (priority 100). The original single-manifest test was unpassable (poisoned tool IS the winner).
11. **Task 2 pow fix**: evaluate operands FIRST, THEN bound-check, THEN invoke `operator.pow` — the ordering is the fix. Use thread-guard timeouts (NOT `signal.alarm` — Windows).
12. **Task 9 allowlist**: `visit()` dispatches ALL nodes — must allowlist `ast.Call` AND `ast.Name` or `visit_Call` is dead code.
13. **Task 10 depth guard**: `contextvars.ContextVar`, NOT a module counter (ParallelExecutor gather branches share module state).
14. **Task 11**: `create_tool` is LIVE (both executors use it) — keep it. When deleting `resolver`, update every construction site: `Orchestrator.create`, `_create_child_orchestrator`, `from_task_file`, 4 test fixtures; wire `--parallel` through `from_task_file`.
15. **Queue (T5/T13)**: per-message reply topics (`reply.{message_id}`), unsubscribe API, snapshot iteration in `process()`, drain loop racing `reply_queue.get()` in `submit_and_wait`, timeout cleanup, tz-aware timestamps. Label the in-process trust boundary honestly — no fake HMAC theater.
16. **Semantic**: keep + wire `--semantic` (tested, cheap); add `temp`→"temperature" synonym so the demo routes; fix empty-query 0.5. LLM embedding upgrade (free `gemini-embedding-001`!) is the documented FUTURE path, not v1.
17. **LLM layer**: stdlib-only via `urllib.request`; no `openai`/`httpx`/`requests` (T19 greps for it). Defaults: OpenRouter `:free` (router), Gemini native `gemini-3.6-flash` (quality/JSON), Groq `openai/gpt-oss-120b` (speed/strict). Agent mode = single-turn NL→plan→execute v1; multi-turn loop = future.

**Deferred / rejected (do not reopen without user approval):** delete semantic router (rejected — it's wired + tested); union-per-step scopes (rejected — reopens H-2); openai SDK (rejected — dependency); multi-turn agent loop v1 (deferred); Together/Perplexity/DeepSeek as defaults (no free tier / paid). Cerebras free tier = expiring trial credits + card — treat as test-only.

---

## 6. Verified free-LLM landscape (Aug 2026 — coded against by T20-23)

Base facts verified against official docs by research agents on 2026-08-13. Full detail in `docs/free-llm.md` (T23) and research reports.

**Default providers (all OpenAI-compatible):
- **OpenRouter** `https://openrouter.ai/api/v1` — `OPENROUTER_API_KEY`; `:free` suffix models (e.g. `nvidia/nemotron-3-ultra-550b-a55b:free`; roster rotates — discovery via `GET /api/v1/models`, filter `pricing.prompt == "0"`); free caps **20 RPM / 50 RPD** (<$10 lifetime credits, then 1,000 RPD); 402 if balance < 0 even on free models; JSON mode passes through (per-model).
- **Gemini AI Studio** — `GEMINI_API_KEY`; native REST `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, header `x-goog-api-key`, body `{contents:[{role,parts:[{text}]}], systemInstruction, generationConfig:{responseMimeType:"application/json"}}`; model **`gemini-3.6-flash`** free (2.5-flash shutdown Oct 16 2026); ~15 RPM / 1.5K RPD; 429 = `RESOURCE_EXHAUSTED`; **`gemini-embedding-001` is free** → future semantic upgrade. OpenAI-compat gateway exists (`/v1beta/openai/`) but native REST preferred (stronger JSON guarantee).
- **Groq** `https://api.groq.com/openai/v1` — `GROQ_API_KEY`; **`openai/gpt-oss-120b`** (30 RPM / 1K RPD / 200K TPD) or `llama-3.3-70b-versatile`; `response_format` with `strict:true` JSON schema supported on gpt-oss; `x-ratelimit-*` headers always present; `Retry-After` on 429.
- **MockProvider** — offline default; fixed valid plan JSON; zero keys. Tests NEVER hit the network.

**Others (honorable mentions / test-only):** Z.AI `glm-4.7-flash` (permanent free, ~1 rps), Mistral free mode (~1B tok/mo, 2 RPM), NVIDIA NIM trial (~40 RPM), OVH AI Endpoints (400 RPM authed), GitHub Models, Ollama Cloud, SambaNova. **Avoid at $0: Together (needs $5), Cerebras (expiring credits + card), DeepSeek (paid), Perplexity (paid), HF inference ($0.10/mo — too small).**

**Client hardening rules (from research):** `retry_with_backoff` honoring `Retry-After` on 429/5xx (3 attempts); 400/401/402/403 raise immediately with friendly messages; `response_format: json_object` alone is NOT sufficient — system message must embed the exact JSON schema with few-shot; post-parse fallback: strip markdown fences → extract first `{...}` block → then fail cleanly.

---

## 7. AUTOPLAN review pipeline state (before you build)

1. ✅ Audit (3 parallel agents) → 5.0/10 → delivered.
2. ✅ Brainstorming gate → decisions 1-2 above → `plan.md` written.
3. ✅ **CEO review** (Phase 1) → decision rows 1-7 applied (named-user criterion, T0 added, CI+LICENSE, T18→T19 merge, mocks kept, semantic kept).
4. ✅ **Eng review** (Phase 3) → decision rows 8-18 applied (F-1..F-11; the critical F-1 is the Task-4 test fix above).
5. ✅ **Free-LLM research** (2 parallel agents, 2026-08-13) → Phase 3.5 added (rows 19-21).
6. ⏳ **DX review** (Phase 3.5, planned next): CLI ergonomics, TTHW, docs walkthrough.
7. ⏳ **Final approval gate** (Phase 4): user picks A (approve) / B (approve w/ overrides) / C (rework). **Build starts only after this.**

---

## 8. Environment & tooling (gotchas)

- **Venv:** `.venv/` in repo root. Tests: `source .venv/bin/activate && python -m pytest tests/ -q` → **41 passed, 35 warnings** (baseline). NOTE: `.venv/bin/pytest` fails (packaging) — T15 fixes.
- **Python 3.12.** Pydantic `>=2.6,<3`, PyYAML `>=6.0,<7` (floor-pinned — do not upgrade).
- **Permissions (opencode agent):** external writes ONLY under `/tmp/opencode/*` and `/home/kisuke/.local/share/opencode/tool-output/*`. Skill files, `~/.gstack`, etc. are READ-BLOCKED. Autoplan methodology (6 decision principles, phase steps, gate formats) lives in `/home/kisuke/.local/share/opencode/tool-output/tool_ffb09632f001iAUOD19v2PxWUu` (99.7KB) — read from there if needed.
- **Codex:** installed but BROKEN (`codex exec` → 401 invalid key). All subagent reviews run on Claude-type agent only. Don't waste a build cycle retrying.
- **Git:** repo dirty-ish: untracked `plan.md`, `src/__init__.py`, 3 stray `test_*_audit.jsonl`. Only commit when explicitly asked.
- **Restore point:** full pre-review `plan.md` saved at `/tmp/opencode/plan-restore-*.md` (latest).
- **CI design (T15):** GitHub Actions `python -m pytest tests/ -q` + `python -m compileall src tests` on 3.12. CI must remain network-free (no live LLM calls).

---

## 9. Build-day execution playbook

1. Get user's **A/B/C approval** at the gate (section 7). Lock remaining taste decisions (rows 6-7, marked Taste→gate).
2. Run **DX review** (1 subagent) then the gate — or gate first if user is impatient, then DX as T16's review.
3. Execute with **superpowers:subagent-driven-development** (plan.md line 3: REQUIRED sub-skill). One subagent PER task per wave; tasks in the same phase run in parallel; TDD per task (failing test → verify fail → implement → pass → full suite).
4. Task order constraints (section 4) are mandatory: T0 first; T5→T13; T9→T14; Phase 3.5 after Phase 3; T19 last.
5. **Verify everything manually** before declaring done: full suite, compileall, grep sweeps (T19 Step 4), demos, `git status` clean of strays, audit traceability table (finding ID → test → status).
6. Final: rewrite Task 19's rating table with real results (target Security 9, Crash-safety 9, DX 9, Overall 9+); update this handover's status section.

**Per-task pattern (from plan.md conventions):** Files → Step 1 failing test → Step 2 verify fail → Step 3 implement (with `# ponytail:` comments on simplifications) → Step 4 pass → Step 5 full suite green. Type hints correct (no `Any` for known types). All timestamps tz-aware UTC (`isoformat()` with `Z`).

---

## 10. Handover checklist — what the next person needs

- [ ] Read `plan.md` fully (it is the source of truth; this file is the map).
- [ ] Run the baseline: `python -m pytest tests/ -q` → expect 41 passed (pre-build) or all green (post-build).
- [ ] Get API keys ONLY if running live LLM demos: `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` — the agent runs keyless with `--provider mock`.
- [ ] Respect the 5 user-locked decisions (section 5.1-5.5) and the review decisions (5.8-5.17) — especially: never union token scopes, never prune registry to empty, never re-add `signal.alarm`, never re-add `httpx`/`requests`/`openai` to `src/llm`, never write tests to repo root.
- [ ] Do NOT skip the plan-first gate if the project is handed to you pre-approval.
- [ ] Know the failure-prone spots: `_run_with_fallback` scope check vs fallback (executor.py:98-132), `_create_child_orchestrator` (orchestrator.py:79), `issue_token` (permission.py:15-26), reply-topic logic (message_queue.py:99-115), `visit()` allowlist (mock_calculator.py:49-52).
- [ ] After build: update this file's status/tables; keep the decision trail in `plan.md` append-only (rows 22+).

---

## 11. Open questions (for the approver)

1. **Taste decisions** (rows 6-7: MessageQueue honesty labeling; semantic keep+wiring) — default: proceed as planned.
2. **DX review** — run before or after the gate? Default: before final gate (part of the 10/10 definition).
3. **Live-LLM demo in CI?** Default: NO (network-free CI). Live demos are human-run via `agent --provider <x>`.
4. **Multi-turn agent loop** — explicitly deferred to v2; flag if the user wants it in v1.