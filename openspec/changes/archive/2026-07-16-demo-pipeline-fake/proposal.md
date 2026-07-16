## Why

The existing `demo.py` prints raw JSON dumps at HITL suspension points — users can't see the pipeline flow. Replace it with `demo_fake.py` that shows every phase from bootstrap to final_delivery with human-readable progress.

## What Changes

- New `agent/scripts/demo_fake.py`: independent script (no flag, no shared code). Full-fake graph with pipeline progress display.
- Each phase prints a readable line: `→ phase_name   description`. HITL points use `⏸`.
- `make demo` and `make demo-scripted` point to `demo_fake.py`.
- The original `demo.py` is deleted.

## Capabilities

None — demo UX improvement.

## Impact

- **Source**: new `demo_fake.py`, delete `demo.py`, update `Makefile`.
- **Graph**: no changes.
