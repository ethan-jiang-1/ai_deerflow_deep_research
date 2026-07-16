> req: WOU-003

## MODIFIED Requirements

### Requirement: Deterministic submit validation fails closed

> Modified from work-unit-kernel WOU-003

Submit validation SHALL additionally enforce: per-topic new-source floor with
`is_new_vs_wave0` checking, Wave0-URL deduplication, and post-submit critic
invocation for `wave1.source-intake` candidates. Existing fixture and wave0
validation paths are unchanged.

#### Scenario: Wave0-duplicate URL does not satisfy new-source floor
- **WHEN** a wave1 candidate carries only sources with `is_new_vs_wave0=false`
- **THEN** submit validation fails with a typed insufficiency code and no SubmissionRecord is appended

#### Scenario: Post-submit critics are invoked
- **WHEN** a wave1 candidate is accepted
- **THEN** SourceDiagnostic and ClaimVerifier critics run on the new evidence and write verdict artifacts
