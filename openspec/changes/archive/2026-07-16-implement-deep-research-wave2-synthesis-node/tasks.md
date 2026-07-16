## 1. Domain model

- [ ] 1.1 Add red tests for frozen SynthesisFinding, FindingIndex, CrossTopicRelation models. @impl WSN-001
- [ ] 1.2 Implement domain/synthesis.py until 1.1 green. @impl WSN-001

## 2. Prompts

- [ ] 2.1 Add red tests for build_synthesis_prompt(accepted_refs, claims, verdicts). @impl WSN-001
- [ ] 2.2 Implement graph/nodes/wave2_synthesis/prompts.py. @impl WSN-001

## 3. Materializer

- [ ] 3.1 Add red tests for materialize_synthesis(result, workspace_root). @impl WSN-002
- [ ] 3.2 Implement graph/nodes/wave2_synthesis/materializer.py. @impl WSN-002

## 4. Real node factory

- [ ] 4.1 Add red tests for real wave2_synthesis factory calling run_agent with zero-tool policy. @impl WSN-001
- [ ] 4.2 Implement graph/nodes/wave2_synthesis/node.py replacing UNAVAILABLE_REAL_FACTORY. @impl WSN-001

## 5. Gate + recipe

- [ ] 5.1 Add real wave2_synthesis gate. @impl WSN-003
- [ ] 5.2 Wire recipe dependency: wave2_synthesis requires wave1. @impl WSN-004

## 6. Tests + governance

- [ ] 6.1 Add impl-map test for full chain including wave2_synthesis. @impl WSN-004
- [ ] 6.2 Add E2E + full-fake regression. @impl WSN-004
- [ ] 6.3 Update project-structure.toml, AGENTS.md, docs. @impl PRS-001..004
- [ ] 6.4 Run full suite, format, lint, governance checks.

## 7. Verify

- [ ] 7.1 make test && make format && make lint
- [ ] 7.2 All governance checks pass
- [ ] 7.3 openspec validate --strict
