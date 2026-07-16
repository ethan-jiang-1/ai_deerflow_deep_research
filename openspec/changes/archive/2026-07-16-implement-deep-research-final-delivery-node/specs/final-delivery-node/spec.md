> req: FID-001, FID-002, FID-003, FID-004, FID-005

## ADDED Requirements

### Requirement: Writer produces report and claim-citation map

The final delivery node SHALL produce `report.md` and `claim-citation-map.json` from the readiness report plan. Writer SHALL be a bounded read-only agent without web tools. Initial implementation uses deterministic formatter; LLM writer is deferred.

#### Scenario: Writer produces report from report plan
- **WHEN** the readiness report plan is available
- **THEN** report.md is produced with findings and citations

#### Scenario: Writer handles missing report plan
- **WHEN** no readiness report plan is available
- **THEN** a minimal report with a note is produced

### Requirement: Integrity gate verifies report and evidence

The final integrity gate SHALL verify report artifacts exist and accepted evidence is present. Missing artifacts SHALL route to self-repair. Missing evidence SHALL route to evidence_blocked.

#### Scenario: Report artifacts present routes to pass
- **WHEN** report_refs is non-empty and evidence exists
- **THEN** the gate returns pass

#### Scenario: Missing artifacts routes to repair
- **WHEN** report_refs is empty
- **THEN** the gate routes to repair (self-repair loop)

### Requirement: Report bounded by report plan

Report conclusions SHALL be bounded by the readiness report plan. Mandatory uncertainties SHALL be preserved.

#### Scenario: Uncertainties preserved in report
- **WHEN** the report plan has mandatory uncertainties
- **THEN** the report includes them

### Requirement: Completed lifecycle idempotent

After gate pass, terminal_status SHALL be COMPLETED. Status/resume/cancel after completion SHALL return stable terminal state.

#### Scenario: Completion produces stable terminal state
- **WHEN** the final delivery node completes
- **THEN** terminal_status is COMPLETED

### Requirement: Mixed-graph integration

Real final delivery SHALL require readiness=real. Full-fake path preserved. Topology unchanged.

#### Scenario: Real final_delivery requires real readiness
- **WHEN** final_delivery=real without readiness=real
- **THEN** recipe construction fails
