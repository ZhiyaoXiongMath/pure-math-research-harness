"""Phase 0 CLI: local identity/help only, without legacy imports or side effects."""

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    """Show bootstrap metadata; reject every research/control operation."""
    parser = argparse.ArgumentParser(
        prog="pmrh",
        description=(
            "Pure Math Research Harness — Phase 0 bootstrap only. "
            "No research, control, model, or project commands are implemented."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"pmrh {__version__} (Phase 0 bootstrap)"
    )
    parser.add_argument("command", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if options.command is not None:
        print(
            f"pmrh: unsupported/not implemented command: {options.command!r}; "
            "Phase 0 CLI cannot run research or control operations.",
            file=sys.stderr,
        )
        return 2
    parser.print_help()
    return 0
