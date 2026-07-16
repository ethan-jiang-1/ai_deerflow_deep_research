## 1. Gap router + worker

- [ ] 1.1 Add red tests for materialize_gap_intents(synthesis_gaps) producing WorkIntents. @impl TEL-001
- [ ] 1.2 Implement gap router in targeted_evidence/subgraph.py. @impl TEL-001
- [ ] 1.3 Add red tests for run_targeted_worker(capabilities, gap, spec). @impl TEL-002
- [ ] 1.4 Implement targeted worker. @impl TEL-002

## 2. Gate + recipe

- [ ] 2.1 Add convergence gate with round budget. @impl TEL-003
- [ ] 2.2 Wire recipe dependency: targeted_evidence loop requires wave2_synthesis real. @impl TEL-004

## 3. Tests + verify

- [ ] 3.1 Add impl-map test for full chain. @impl TEL-004
- [ ] 3.2 Run full suite, format, lint, governance. @impl TEL-001..004
