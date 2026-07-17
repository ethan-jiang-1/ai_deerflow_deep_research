#!/usr/bin/env python3
"""Strict preflight for manually selected full-real release acceptance.

@impl EVH-005
@impl EVH-009
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from tests.scenarios.release import ReleasePreflightError, preflight_release_environment  # noqa: E402


def main() -> int:
    if os.environ.get("RELEASE_DISABLE_DOTENV") != "1":
        load_dotenv(AGENT_ROOT / ".env", override=False)
    try:
        environment = preflight_release_environment(environ=os.environ)
    except ReleasePreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Release preflight passed: model={environment.model_provider}, web={environment.web_provider}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
