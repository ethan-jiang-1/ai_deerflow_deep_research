#!/usr/bin/env python3
"""Strict credential preflight for explicitly selected live evaluation.

@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from tests.scenarios.live import LivePreflightError, preflight_live_environment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-web", action="store_true")
    args = parser.parse_args()
    if os.environ.get("LIVE_DISABLE_DOTENV") != "1":
        load_dotenv(AGENT_ROOT / ".env", override=False)
    try:
        environment = preflight_live_environment(environ=os.environ, require_web=args.require_web)
    except LivePreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    providers = [f"model={environment.model_provider}"]
    if environment.web_provider is not None:
        providers.append(f"web={environment.web_provider}")
    print("Live preflight passed: " + ", ".join(providers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
