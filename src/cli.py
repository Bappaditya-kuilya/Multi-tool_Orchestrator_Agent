from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .orchestrator import Orchestrator
from .registry import ToolRegistry

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RUNTIME = 2


class _CliError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    # F-DX-2: usage errors exit 1, not argparse's default 2
    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message:
            self._print_message(message, sys.stderr)
        raise SystemExit(EXIT_USAGE if status == 2 else status)


def _check_audit_path(value: str) -> None:
    # VULN-06: audit log must stay inside the current directory
    path = Path(value)
    if ".." in path.parts:
        raise _CliError("audit file must not contain '..'")
    cwd = Path.cwd().resolve()
    resolved = (cwd / path if not path.is_absolute() else path).resolve()
    if not resolved.is_relative_to(cwd):
        raise _CliError("audit file must be inside the current directory")


def _default_manifests_dir() -> Path:
    # F-DX-3: fall back to repo manifests when CWD has none
    cwd_manifests = Path.cwd() / "manifests"
    if cwd_manifests.is_dir():
        return cwd_manifests
    return Path(__file__).resolve().parent.parent / "manifests"


def _build_parser() -> _Parser:
    parser = _Parser(prog="python -m src.cli", description="Multi-Tool Orchestrator Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p_run = sub.add_parser("run", help="run a task file")
    p_run.add_argument("task_file", help="path to task JSON file")
    p_run.add_argument("manifests_dir", nargs="?", default=None, help="tool manifests dir (default: ./manifests)")
    p_run.add_argument("--audit-file", default="audit.jsonl", help="audit log path (must stay inside CWD)")
    p_run.add_argument("--output-file", default=None, help="write JSON results to this file instead of stdout")
    p_run.add_argument("--parallel", action="store_true", help="run independent steps in parallel")
    p_run.add_argument("--semantic", action="store_true", help="use semantic capability matching")

    p_list = sub.add_parser("list-tools", help="list tools from a manifests dir")
    p_list.add_argument("manifests_dir", nargs="?", default=None, help="tool manifests dir (default: ./manifests)")

    p_validate = sub.add_parser("validate", help="validate a manifests dir")
    p_validate.add_argument("manifests_dir", nargs="?", default=None, help="tool manifests dir (default: ./manifests)")

    return parser


def _cmd_run(args) -> int:
    _check_audit_path(args.audit_file)
    manifests_dir = args.manifests_dir or _default_manifests_dir()
    orch, task = Orchestrator.from_task_file(args.task_file, manifests_dir, args.audit_file)
    result = asyncio.run(orch.run_task(task))

    if args.output_file:
        Path(args.output_file).write_text(json.dumps(result, indent=2))
        print(f"Results written to {args.output_file}")
    else:
        print(json.dumps(result, indent=2))

    print(f"Audit log written to {args.audit_file}")
    return EXIT_OK


def _cmd_list_tools(args) -> int:
    manifests_dir = args.manifests_dir or _default_manifests_dir()
    registry = ToolRegistry()
    registry.load_manifests(Path(manifests_dir))
    for tool in registry.all_tools():
        print(f"{tool.name} (priority={tool.priority}): {tool.capability_tags}")
    return EXIT_OK


def _cmd_validate(args) -> int:
    manifests_dir = args.manifests_dir or _default_manifests_dir()
    registry = ToolRegistry()
    registry.load_manifests(Path(manifests_dir))
    print(f"All {len(registry.all_tools())} manifests are valid")
    return EXIT_OK


_HANDLERS = {"run": _cmd_run, "list-tools": _cmd_list_tools, "validate": _cmd_validate}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _HANDLERS[args.command](args)
    except _CliError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_RUNTIME
    except BrokenPipeError:
        raise
    except KeyboardInterrupt:
        raise
    except SystemExit:
        raise
    except Exception as e:  # F-DX-6: catch Exception only, never BaseException
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())