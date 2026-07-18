# Plan: Deep Research Six-Case Live Closure

> Type: risk acceptance / validation follow-up | Updated: 2026-07-18 | Status: deferred

## Background / Current State

`harden-late-node-structured-output` has completed its production changes, focused
TDD, deterministic suites, static governance, and repository-boundary checks. The
remaining uncertainty is provider-dependent: the complete six-case credentialed
live lane has not produced six passing case reports in one fresh run.

The latest complete run at
`agent/.reports/live-evidence-v1-20260718-185139` passed five live cases plus both
preflight tests and failed the targeted-evidence case after the provider proposed
three parallel searches. The cumulative request quota correctly denied the batch
before dispatch. A later focused targeted diagnostic reached the provider but
exceeded its declared 180-second deadline. Earlier complete runs and their exact
typed failures remain recorded in both owning OpenSpec task files.

This is not evidence that the deterministic implementation is green on the current
provider distribution. It is also not a reason to keep the bounded production fix
open indefinitely: the failing paths are fail-closed, publish no invalid authority,
and are covered at their lowest stable seams by deterministic tests.

## Deferral Decision

Defer further credentialed retries. Archive readiness for
`harden-late-node-structured-output` may rely on its completed deterministic and
governance gates, while explicitly declining the claim that the six-case live lane
is green.

The owning `rebalance-deep-research-test-assets` tasks 6.7, 6.8, and 7.4 remain
open. `.github/workflows/agent-live-evaluation.yml` remains manual-only with the
unchanged 20-minute timeout. Historical release attestation does not substitute for
current six-case provider compatibility.

## Re-entry Triggers

Reopen this plan through a reviewed OpenSpec change when any one of these applies:

- nightly live evaluation is proposed for restoration;
- a release decision needs current-provider evidence rather than the committed
  historical attestation;
- the selected model, web provider, bridge budget, or late-node prompts materially
  change;
- Wave1, Wave2, or targeted-evidence behavior changes at a live dependency seam;
- an operator explicitly allocates one bounded credentialed validation window.

Provider-only variance by itself does not authorize production loosening, parser
coercion, deadline increases, or selective case reruns.

## Execution Contract

1. Pass strict model/web preflight from `agent/.env`.
2. Create one fresh evidence-v1 report root and fresh thread/run/research identities.
3. Run the complete selector exactly once:
   `pytest -m "requires_llm and not release_e2e" -q`.
4. Preserve every case report, including failures; do not selectively rerun a case
   to manufacture a green aggregate.
5. Scan the archive for the exact six-case set, schema validity, bounds, uniqueness,
   and redaction.
6. If red, diagnose at the lowest responsible deterministic seam before proposing
   production changes. A new production change requires its own review and TDD.

## Completion Criteria

- all six live cases pass in one fresh complete run;
- all six evidence-v1 reports and the aggregate pass schema/redaction scanning;
- declared case wall-time remains at most 900 seconds and preserves the five-minute
  margin inside the unchanged 20-minute job timeout;
- model/tool/token/cost-availability/retry/invariant/metric evidence is recorded;
- `rebalance-deep-research-test-assets` tasks 6.7 and 6.8 are completed and the
  reviewed six-case nightly schedule is restored;
- task 7.4 is reassessed without running release E2E unless its separate trigger is
  actually met.

## Risks / Trade-offs

- [Risk] Current-provider compatibility remains unproven as a six-case aggregate.
  -> Keep the lane manual-only and make no nightly/release claim from partial runs.
- [Risk] Deferral becomes invisible debt. -> Keep this plan linked from both
  authoritative task files and the active-plan index.
- [Risk] A future retry repeats expensive exploratory loops. -> Retain the exact
  reports, typed failure history, one-shot rule, and lowest-seam diagnosis rule.

## Implementation Link

The production implementation is owned by
`openspec/changes/harden-late-node-structured-output`. Live aggregation and cadence
remain owned by `openspec/changes/rebalance-deep-research-test-assets`. Any future
production remediation must be proposed as a new OpenSpec change; this plan is not
implementation authorization.
