"""Run the deterministic, synthetic Phase 10 scenarios A–E."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.demo import SCENARIOS, run_all, run_scenario  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all", *SCENARIOS],
        help="scenario to run; default runs A, B, C, D1, D2, and E",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evidence = run_all() if args.scenario == "all" else [run_scenario(args.scenario)]
    if args.json:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    else:
        for item in evidence:
            print(
                "{scenario}: status={status} confidence={confidence} "
                "portal_attempts={portal_attempts} audit_events={audit_events}".format(**item)
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
