"""Inert help/version plus the explicitly read-only DEV03 status command."""

import argparse
import json
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    """Read existing status; reject research/control operations."""
    parser = argparse.ArgumentParser(
        prog="pmrh",
        description=(
            "Pure Math Research Harness — read-only project status. "
            "Help/version are inert; research and control commands are unsupported."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"pmrh {__version__} (Phase 0 bootstrap)"
    )
    parser.add_argument("command", nargs="?", help="status PROJECT --instance INSTANCE --json [--as-of COMMIT]")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if options.command == "status":
        query = argparse.ArgumentParser(prog="pmrh status", allow_abbrev=False,
                                        description="Read one existing journal snapshot without repair or execution.")
        query.add_argument("project")
        query.add_argument("--instance", required=True)
        query.add_argument("--json", action="store_true", required=True)
        query.add_argument("--as-of", metavar="COMMIT", help="Existing full journal commit SHA-256")
        selected = query.parse_args(options.arguments)
        # Exact DEV03 compatibility edge, imported only after argument parsing.
        from research_studio.readonly_query import status
        result = status(selected.project, selected.instance, as_of=selected.as_of)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
        return 0 if result["available"] else 1
    if options.command is not None:
        print(
            f"pmrh: unsupported/not implemented command: {options.command!r}; "
            "CLI cannot run research or control operations.",
            file=sys.stderr,
        )
        return 2
    parser.print_help()
    return 0
