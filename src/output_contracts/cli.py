"""Command line interface: the `output-contracts` console script."""

from __future__ import annotations

import argparse
import json
import sys

from output_contracts import __version__
from output_contracts.redact import STYLES, scan_and_redact
from output_contracts.validate import Contract


def _load_json(path: str) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_validate(args: argparse.Namespace) -> int:
    """Print the validation report as JSON. Exit 1 when invalid."""
    contract = Contract(_load_json(args.contract))  # type: ignore[arg-type]
    report = contract.validate(_load_json(args.input), style=args.style)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.valid else 1


def cmd_redact(args: argparse.Namespace) -> int:
    """Print the input with secrets redacted. Always exits 0."""
    redacted, redactions = scan_and_redact(_load_json(args.input), style=args.style)
    print(json.dumps({"redacted": redacted, "redactions": redactions}, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """CI mode: quiet on success, exit 2 when invalid."""
    contract = Contract(_load_json(args.contract))  # type: ignore[arg-type]
    report = contract.validate(_load_json(args.input), style=args.style)
    if report.valid:
        return 0
    for error in report.errors:
        detail = f"{error['path']}: {error['message']} (expected {error['expected']})"
        print(detail, file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="output-contracts",
        description="Validate and redact structured tool outputs before the model sees them.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="validate input against a contract")
    p_validate.add_argument("--contract", required=True, help="contract JSON file")
    p_validate.add_argument("--input", required=True, help="tool output JSON file")
    p_validate.add_argument("--style", choices=list(STYLES), default="full")
    p_validate.set_defaults(func=cmd_validate)

    p_redact = sub.add_parser("redact", help="redact secrets in a JSON file")
    p_redact.add_argument("--input", required=True, help="tool output JSON file")
    p_redact.add_argument("--style", choices=list(STYLES), default="full")
    p_redact.set_defaults(func=cmd_redact)

    p_check = sub.add_parser("check", help="CI mode: exit 2 when invalid, quiet on success")
    p_check.add_argument("--contract", required=True, help="contract JSON file")
    p_check.add_argument("--input", required=True, help="tool output JSON file")
    p_check.add_argument("--style", choices=list(STYLES), default="full")
    p_check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
