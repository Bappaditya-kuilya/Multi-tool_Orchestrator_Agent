# Multi-Tool Orchestrator Agent

A permission-scoped multi-tool orchestration agent for learning and reference. Implements a complete pipeline: **registry → router → permission → executor → orchestrator → auditor**, with an optional distributed mode via in-process message queue.

## Quickstart

```bash
# Install (from repo root)
pip install -e .

# Run a demo task
python -m src.cli run examples/demo-task.json

# Run with parallel execution
python -m src.cli run --parallel examples/demo-task.json

# Run with semantic capability matching
python -m src.cli run --semantic examples/demo-task.json

# List available tools
python -m src.cli list-tools

# Validate manifests
python -m src.cli validate
```

## Architecture

```
Task JSON → Registry (YAML manifests) → Router (exact/semantic) 
    → PermissionScoper (token with scopes) → Executor (sequential/parallel)
    → Tools (mock: weather, wikipedia, calculator, github-search)
    → AuditLog (JSONL)
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `src/registry.py` | Loads YAML tool manifests, indexes by name and capability |
| `src/router.py` | Maps capability → tools (exact tag match + semantic fallback) |
| `src/permission.py` | Issues tokens with granted scopes from winning tools |
| `src/executor.py` | Runs steps with dependency scheduling + fallback |
| `src/orchestrator.py` | Coordinates pipeline, handles sub-tasks with scope confinement |
| `src/auditor.py` | Append-only JSONL audit trail of every tool invocation |
| `src/message_queue.py` | In-process message queue for distributed mode |
| `src/semantic.py` | Zero-dependency TF-IDF + synonym matcher |

### Tools (Mock)

| Tool | Capability | Description |
|------|------------|-------------|
| `mock-weather` | `weather` | Weather for 5 cities (deterministic with seed) |
| `mock-wikipedia` | `wikipedia` | Article summaries for 3 topics |
| `mock-calculator` | `calculator` | Safe eval: + - * / // % ** unary |
| `mock-calculator-advanced` | `calculator` | Advanced: sqrt, abs, round, min, max |
| `mock-github-search` | `github-search` | Search 3 repos (pydantic, fastapi, httpx) |

## CLI Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Usage error (bad args, unknown command) |
| 2 | Runtime error (task failed, file not found, etc.) |

## Adding a New Tool (15-minute guide)

### 1. Create a manifest YAML

```yaml
# manifests/mock-time.yaml
name: "mock-time"
display_name: "Mock Time Tool"
description: "Returns current time"
capability_tags:
  - "time"
input_schema:
  type: "object"
  properties:
    format:
      type: "string"
      enum: ["iso", "unix", "readable"]
output_schema:
  type: "object"
  properties:
    time:
      type: "string"
required_scope: "time:read"
priority: 10
```

### 2. Implement the tool class

```python
# src/tools/mock_time.py
from __future__ import annotations
import asyncio
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
        else:
            return {"time": now.strftime("%Y-%m-%d %H:%M:%S UTC")}
```

### 3. Register the tool

```python
# src/tools/__init__.py - add to TOOL_CLASSES
from .mock_time import MockTimeTool

TOOL_CLASSES = {
    # ... existing tools ...
    "mock-time": MockTimeTool,
}
```

### 4. Test it

```bash
# Create a task
cat > test-time.json << 'EOF'
{
  "task_id": "time-test",
  "steps": [
    {"id": "t1", "capability": "time", "input": {"format": "iso"}}
  ]
}
EOF

# Run it
python -m src.cli run test-time.json
```

### 5. Add a test (optional but recommended)

```python
# tests/test_tools.py
def test_time_tool():
    from src.tools.mock_time import MockTimeTool
    from src.models import ToolManifest
    
    manifest = ToolManifest(
        name="mock-time",
        capability_tags=["time"],
        required_scope="time:read",
        priority=10,
    )
    tool = MockTimeTool(manifest)
    result = asyncio.run(tool.execute({"format": "iso"}))
    assert "time" in result
```

## Free-LLM Layer (Stretch)

The agent can run at $0 using free providers:
- **MockProvider** — offline default, zero API keys
- **OpenRouter** — `openrouter/free` model
- **Gemini** — `gemini-3.6-flash` with native JSON mode
- **Groq** — `openai/gpt-oss-120b` for speed

See `src/llm/providers.py` for the stdlib-only implementation (`urllib.request` only).

## Running Tests

```bash
# All tests
python -m pytest tests/ -q

# Security tests
python -m pytest tests/test_security_*.py -q

# Attack regression tests
python -m pytest tests/test_attacks.py -q

# From any directory (CWD-independent)
python -m pytest /path/to/Multi-Tool_Orchestrator_Agent/tests/ -q
```

## Security Features

- **Sub-task confinement**: Child orchestrators only get scopes intersecting with parent token
- **Token inflation prevention**: Only winner's scope granted per step
- **Reply-topic isolation**: Per-message unique reply topics with correlation IDs
- **CPU DoS protection**: Exponent bounds in calculator (`**` capped at 1000)
- **Graceful failures**: No raw tracebacks, clean error messages
- **Audit resilience**: Corrupt-line tolerant JSONL reader

## License

MIT