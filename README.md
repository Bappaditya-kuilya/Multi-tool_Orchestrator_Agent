# Multi-Tool Orchestrator Agent

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/Tests-124%20passing-brightgreen?logo=pytest" alt="124 tests passing">
  <img src="https://img.shields.io/badge/Zero%20Warnings-success?logo=python" alt="Zero warnings">
  <img src="https://img.shields.io/badge/License-MIT-yellow?logo=opensourceinitiative" alt="MIT License">
  <img src="https://img.shields.io/badge/Security-9.5%2F10-critical?logo=security" alt="Security 9.5/10">
</p>

A permission-scoped multi-tool orchestration agent for learning and reference. Run complex multi-step tasks with tool routing, scope confinement, and audit trails — all in ~1,500 lines of Python.

---

## Get Running in 30 Seconds

```bash
git clone https://github.com/Bappaditya-kuilya/Multi-tool_Orchestrator_Agent
cd Multi-tool_Orchestrator_Agent
pip install -e .

# Run the demo (4 tools, sequential)
python -m src.cli run examples/demo-task.json

# Run the demo in parallel
python -m src.cli run --parallel examples/demo-task.json

# Use semantic capability matching
python -m src.cli run --semantic examples/demo-task.json
```

---

## How It Works

A task is a JSON file with steps. Each step names a capability (`weather`, `calculator`, etc.) and the orchestrator routes it to the right tool.

### The Pipeline

```mermaid
flowchart LR
    subgraph Input
        A[Task JSON]
    end

    subgraph Core
        B[Registry<br/>loads YAML manifests]
        C[Router<br/>exact tag match<br/>then semantic fallback]
        D[PermissionScoper<br/>issues scoped token]
        E[Executor<br/>sequential or parallel]
        F[AuditLog<br/>JSONL trail]
    end

    subgraph Tools
        G1[Weather]
        G2[Wikipedia]
        G3[Calculator]
        G4[GitHub Search]
    end

    A --> B --> C --> D --> E
    E --> F
    E --> G1 & G2 & G3 & G4

    classDef core fill:#e3f2fd,stroke:#1976d2,stroke-width:2px;
    classDef tools fill:#fff3e0,stroke:#f57c00,stroke-width:2px;

    class B,C,D,E,F core;
    class G1,G2,G3,G4 tools;
```

### Step Execution (with Fallbacks)

```mermaid
flowchart TD
    S[Step arrives] --> R{Router finds tools?}
    R -->|No| F1[Fail: No tool for capability]
    R -->|Yes| P{Permission check}
    P -->|Denied| N[Skip tool, try next]
    P -->|Granted| T[Run tool]
    T -->|Success| OK[Return result]
    T -->|Exception| N
    N -->|More tools?| P
    N -->|No more| F2[Fail: all fallbacks exhausted]

    classDef fail fill:#ffebee,stroke:#c62828,stroke-width:2px;
    classDef ok fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef check fill:#fff3e0,stroke:#f57c00,stroke-width:2px;

    class F1,F2 fail;
    class OK ok;
    class R,P check;
```

### Security: Sub-task Confinement

```mermaid
flowchart LR
    P[Parent Token<br/>scopes: A, B, C] -->|intersect| C[Child Token<br/>scopes: A, B]
    C --> T1[Tool A]
    C --> T2[Tool B]
    C -.->|blocked| T3[Tool C]

    classDef parent fill:#e3f2fd,stroke:#1976d2,stroke-width:2px;
    classDef child fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef blocked fill:#ffebee,stroke:#c62828,stroke-width:2px,stroke-dasharray:5;

    class P parent;
    class C,T1,T2 child;
    class T3 blocked;
```

---

## Quick Commands

| Command | What it does |
|---------|--------------|
| `python -m src.cli run <task.json>` | Execute a task |
| `python -m src.cli run --parallel <task.json>` | Run independent steps in parallel |
| `python -m src.cli run --semantic <task.json>` | Use semantic capability matching |
| `python -m src.cli list-tools` | Show all available tools |
| `python -m src.cli validate` | Validate manifest directory |

**Exit codes:** `0` = success, `1` = usage error, `2` = runtime error

---

## The Demo Task

```json
{
  "task_id": "demo-1",
  "steps": [
    {"id": "calc-1", "capability": "calculator", "input": {"expression": "2 + 2 * 3"}},
    {"id": "weather-1", "capability": "weather", "input": {"location": "London"}},
    {"id": "wiki-1", "capability": "wikipedia", "input": {"query": "Python (programming language)"}},
    {"id": "gh-1", "capability": "github-search", "input": {"query": "pydantic"}}
  ]
}
```

Run it:
```bash
python -m src.cli run examples/demo-task.json
```

Output:
```json
{
  "task_id": "demo-1",
  "results": {
    "calc-1": {"success": true, "output": {"expression": "2 + 2 * 3", "result": 8.0}},
    "weather-1": {"success": true, "output": {"location": "London", "temperature_c": 18, "condition": "Cloudy", "humidity": 80}},
    "wiki-1": {"success": true, "output": {"title": "Python (programming language)", "summary": "Python is a high-level...", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)"}},
    "gh-1": {"success": true, "output": {"total_count": 42, "items": [{"name": "pydantic", "full_name": "pydantic/pydantic", "description": "Data validation...", "stargazers_count": 15000, "html_url": "https://github.com/pydantic/pydantic"}]}}
  }
}
```

---

## Add a New Tool in 3 Steps

### 1. Create a manifest

```yaml
# manifests/mock-time.yaml
name: "mock-time"
display_name: "Mock Time Tool"
capability_tags: ["time"]
required_scope: "time:read"
priority: 10
input_schema:
  type: "object"
  properties:
    format:
      type: "string"
      enum: ["iso", "unix", "readable"]
output_schema:
  type: "object"
  properties:
    time: {type: "string"}
```

### 2. Implement the tool

```python
# src/tools/mock_time.py
from __future__ import annotations
import datetime
from typing import Any
from .base import BaseTool

class MockTimeTool(BaseTool):
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        fmt = input_data.get("format", "iso")
        now = datetime.datetime.now(datetime.timezone.utc)
        if fmt == "iso":
            return {"time": now.isoformat()}
        elif fmt == "unix":
            return {"time": str(int(now.timestamp()))}
        return {"time": now.strftime("%Y-%m-%d %H:%M:%S UTC")}
```

### 3. Register it

```python
# src/tools/__init__.py
from .mock_time import MockTimeTool

TOOL_CLASSES = {
    # ... existing ...
    "mock-time": MockTimeTool,
}
```

### 4. Test it

```bash
python -m src.cli run <(echo '{"task_id":"t","steps":[{"id":"t1","capability":"time","input":{"format":"iso"}}]}')
```

---

## Built-in Tools (Mock)

| Tool | Capability | What it does |
|------|------------|--------------|
| `mock-weather` | `weather` | Current weather for 5 cities (deterministic with seed) |
| `mock-wikipedia` | `wikipedia` | Article summaries for Python, AI, ML |
| `mock-calculator` | `calculator` | Safe math: `+ - * / // % **` and unary ops |
| `mock-calculator-advanced` | `calculator` | Advanced: `sqrt`, `abs`, `round`, `min`, `max` |
| `mock-github-search` | `github-search` | Search 3 repos: pydantic, fastapi, httpx |

---

## Security

| Feature | How it works |
|---------|--------------|
| **Sub-task confinement** | Child orchestrators only get scopes intersecting with parent token |
| **Token inflation prevention** | Only the winning tool's scope is granted per step |
| **Reply-topic isolation** | Per-message unique reply topics + correlation IDs |
| **CPU DoS protection** | Exponent cap (`**` ≤ 1000), finiteness checks |

### How scope confinement works

A parent task with scopes `["weather:read", "calc:eval", "wiki:read"]` spawns a sub-task requesting `["wiki:read", "github:read"]`. The child only gets `["wiki:read"]` because that's the intersection. `github:read` was never granted to the parent, so the child can't escalate.

---

## Running Tests

```bash
# All 124 tests (0 warnings)
python -m pytest tests/ -q

# Security regression tests
python -m pytest tests/test_security_*.py -q

# Attack regressions
python -m pytest tests/test_attacks.py -q

# From any directory
python -m pytest /path/to/repo/tests/ -q
```

---

## Free-LLM Layer

Run at $0 with free providers — stdlib only (`urllib.request`):

```python
from src.llm.providers import create_provider

# Offline default (zero keys)
provider = create_provider("mock")
plan = await provider.chat([{"role": "user", "content": "Calculate 2+2 and get London weather"}])

# Free providers (when keys available)
provider = create_provider("openrouter")  # openrouter/free
provider = create_provider("gemini")      # gemini-3.6-flash
provider = create_provider("groq")        # openai/gpt-oss-120b
```

---

## Project Structure

```
.
├── .github/workflows/ci.yml    # GitHub Actions: pytest + compileall
├── docs/audit.md               # Full traceability + 9.5/10 rating
├── examples/demo-task.json     # Single demo task
├── manifests/                  # 5 tool YAML manifests
├── src/
│   ├── cli.py                  # CLI with run/list/validate
│   ├── registry.py             # YAML manifest loader
│   ├── router.py               # Exact + semantic routing
│   ├── permission.py           # Token issuance
│   ├── executor.py             # Sequential + parallel execution
│   ├── orchestrator.py         # Pipeline + sub-tasks
│   ├── auditor.py              # JSONL audit trail
│   ├── message_queue.py        # In-process pub/sub
│   ├── semantic.py             # TF-IDF + synonym matcher
│   ├── models.py               # Pydantic models
│   ├── llm/providers.py        # Free-LLM providers
│   └── tools/                  # 5 mock tool implementations
├── tests/                      # 124 tests (security, integration, attacks)
```

---

## Why This Exists

A reference architecture for scoped multi-tool agent orchestration. Read the code, run the demos, extend with one new tool in under 15 minutes. No code path crashes or escalates scopes.

**Target audience:** Backend engineers evaluating permission-scoped tool delegation patterns.

---

## License

MIT — use freely, learn from it, build on it.
