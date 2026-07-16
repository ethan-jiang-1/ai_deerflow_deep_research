## 1. Writer

- [x] 1.1 Implement `graph/nodes/final_delivery/writer.py` — deterministic formatter. @impl FID-001
- [x] 1.2 Add tests for writer output. @impl FID-001

## 2. Gate

- [x] 2.1 Implement `build_final_delivery_real_gate_def()` in `engine/gate_fixtures.py`. @impl FID-002
- [x] 2.2 Re-export in `gate_adapter.py`, wire in `builder.py`. @impl FID-002

## 3. Real factory

- [x] 3.1 Implement `build_real` in `node.py`. @impl FID-001..005
- [x] 3.2 Add tests. @impl FID-001..005

## 4. Recipe + contract

- [x] 4.1 Wire `final_delivery=real` guard in `research.py`. @impl FID-005
- [x] 4.2 Update contract test. @impl FID-005

## 5. Verification

- [x] 5.1 `make test` — 1098 passed.
- [x] 5.2 Governance checks PASS.
- [x] 5.3 No `backend`/`frontend` changes.
