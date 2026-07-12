#!/usr/bin/env python3
"""Deep Research readiness diagnostics as a thin operations CLI.

@impl DEC-005

This CLI calls the reusable ``runtime/diagnostics.py`` and prints the result as
JSON. It never logs secret-bearing data; blocking exit status depends only on
``runtime_ready``.  Entry not-ready/unknown is surfaced but never disables the
global tool.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prelaunch-fingerprint",
        default=None,
        help="Expected startup fingerprint (prelaunch-candidate mode)",
    )
    parser.add_argument(
        "--gateway-workers",
        default=None,
        help="Explicit GATEWAY_WORKERS value (overrides env)",
    )
    args = parser.parse_args()

    os.environ.setdefault(
        "DEER_FLOW_CONFIG_PATH",
        os.environ.get("DEER_FLOW_CONFIG_PATH", str(Path.cwd() / "config.yaml")),
    )
    if args.gateway_workers is not None:
        os.environ["GATEWAY_WORKERS"] = args.gateway_workers

    try:
        from deerflow_deep_research.runtime.diagnostics import run_diagnostics
    except ImportError as exc:
        print(json.dumps({"ok": False, "code": "module_unavailable", "detail": str(exc)}), file=sys.stderr)
        return 1

    expected = args.prelaunch_fingerprint or None
    diag = run_diagnostics(
        expected_fingerprint=expected,
        entry_checks=None,
    )
    output = {
        "ok": diag.runtime_ready,
        "mode": diag.mode,
        "runtime_ready": diag.runtime_ready,
        "entry_ready": diag.entry.status,
        "durability": diag.durability,
        "provider_kind": diag.provider_kind,
        "worker_count": diag.worker_count,
    }
    if diag.issues:
        output["issues"] = diag.issues
    print(json.dumps(output, sort_keys=True))
    return 0 if diag.runtime_ready else 1


if __name__ == "__main__":
    sys.exit(main())
