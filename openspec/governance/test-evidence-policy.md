# Test Evidence Governance Policy

This directory is a project extension to OpenSpec. OpenSpec does not load it
implicitly, so `openspec/config.yaml` and `agent/AGENTS.md` retain short
bootstrap pointers to this policy and the owning specification.

## Authority

| Surface | Authority |
|---|---|
| `openspec/specs/evaluation-hardening/spec.md` | Approved normative test-evidence semantics |
| One active owning `evaluation-hardening` delta | Pending normative modifications during review and apply |
| Test-owned evidence, scenario, incident, node, fault, and discovery registries | Exact enumerable evidence metadata |
| `agent/scripts/check_test_assets.py` and agent tests | Executable collection, joins, validation, and detector smoke coverage |
| `openspec/config.yaml` and human-authored `agent/AGENTS.md` text | Authoring bootstrap, navigation, commands, and concise operational guidance |
| Archived change artifacts | Historical context only |

The active spec/delta lifecycle owns semantics. This policy defines authority,
lifecycle, and synchronization rules only; it does not maintain a competing
evidence catalog, selector list, authenticity vocabulary, or independent
normative requirements. Static registries are reviewable claims and never
substitute for the behavioral evidence of collected tests.

## Lifecycle

The main `evaluation-hardening` spec remains the authority for approved
behavior while one active owning delta describes pending modifications. During
apply, implementation and evidence assets conform to that reviewed delta.
Archive or an explicit spec sync promotes the accepted delta into the main
spec; after that, the archived proposal, design, delta, and tasks are historical
and are not required to discover the current contract.

## Synchronized Changes

A change that adds or modifies test-evidence semantics or executable assets
must:

1. update the owning `evaluation-hardening` delta when normative behavior
   changes;
2. identify the evidence class and lowest responsible production seam using
   the owning spec, and justify escalation to persisted trace replay, live
   dependencies, or full-system acceptance;
3. update only the test-owned enumerable registries whose references change,
   without cataloging unrelated tests;
4. update the agent-owned checker and focused tests for changed executable
   rules; pure validators get direct invalid fixtures, while collectors,
   discovery scans, archive scans, and runtime detectors that could pass on an
   empty or mis-scoped input also get a known-violation smoke case;
5. isolate and restore the mutable process-global state each fixture actually
   changes through public reset or restore APIs; and
6. keep the concise OpenSpec and agent-guide pointers aligned and pass strict
   OpenSpec, requirement, spec, architecture, and applicable agent-owned
   evidence gates before archive.

Test counts, directory placement, line coverage, and static metadata are not
proxies for execution authenticity. Exact selection and evidence semantics
remain in the owning spec and executable agent assets.
