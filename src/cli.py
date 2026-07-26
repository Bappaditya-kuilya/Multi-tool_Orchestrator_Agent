from __future__ import annotations

import json
import asyncio
import sys
from pathlib import Path

from .orchestrator import Orchestrator
from .registry import ToolRegistry


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.cli <command> [args...]")
        print("Commands:")
        print("  run <task_file> [manifests_dir] [audit_file] [output_file]")
        print("  list-tools [manifests_dir]")
        print("  validate [manifests_dir]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "run":
        if len(sys.argv) < 3:
            print("Usage: python -m src.cli run <task_file> [manifests_dir] [audit_file] [output_file]")
            sys.exit(1)
        task_file = sys.argv[2]
        manifests_dir = sys.argv[3] if len(sys.argv) > 3 else "manifests"
        audit_file = sys.argv[4] if len(sys.argv) > 4 else "audit.jsonl"
        output_file = sys.argv[5] if len(sys.argv) > 5 else None

        orch, task = Orchestrator.from_task_file(task_file, manifests_dir, audit_file)
        result = asyncio.run(orch.run_task(task))

        if output_file:
            Path(output_file).write_text(json.dumps(result, indent=2))
            print(f"Results written to {output_file}")
        else:
            print(json.dumps(result, indent=2))

        print(f"Audit log written to {audit_file}")

    elif command == "list-tools":
        manifests_dir = sys.argv[2] if len(sys.argv) > 2 else "manifests"
        registry = ToolRegistry()
        registry.load_manifests(Path(manifests_dir))
        for tool in registry.all_tools():
            print(f"{tool.name} (priority={tool.priority}): {tool.capability_tags}")

    elif command == "validate":
        manifests_dir = sys.argv[2] if len(sys.argv) > 2 else "manifests"
        registry = ToolRegistry()
        try:
            registry.load_manifests(Path(manifests_dir))
            print(f"All {len(registry.all_tools())} manifests are valid")
        except Exception as e:
            print(f"Validation failed: {e}")
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()