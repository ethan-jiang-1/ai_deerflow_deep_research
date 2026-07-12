> req: DEC-003, DEC-004

## MODIFIED Requirements

### Requirement: Public entry skill is committed and enabled

The project SHALL keep the `deep-research-controller` skill source under
`agent/config/public-skill/`, materialize it under `skills/public/`, and store its
enabled state in `extensions_config.json`. The change-01 skill MAY route research
requests to the `start | resume | status | cancel` lifecycle, but SHALL explicitly
surface `implementation_mode=full_fake`, SHALL state that terminal fixtures are not
research findings or reports, and SHALL NOT claim real research completion. It SHALL
NOT contain graph topology, phase prompts, fixture controls, answer payloads, exclusive
tool claims, or security-isolation claims.

#### Scenario: Public skill is available
- **WHEN** configuration is materialized and enabled skills are loaded
- **THEN** the public Deep Research entry skill is discoverable with content matching its committed source

#### Scenario: Full-fake lifecycle is represented honestly
- **WHEN** the entry skill handles a research request or lifecycle result in change 01
- **THEN** it preserves the `full_fake` mode, routes only through the documented control actions, and does not present a terminal fixture as findings, citations, report content, or completed research

#### Scenario: Legacy custom path is rejected
- **WHEN** validation finds the project entry skill under `skills/custom/deep-research-controller/` instead of the public path
- **THEN** the configuration check fails and identifies the legacy location

### Requirement: Dedicated Agent is provisioned in the effective user scope

The project SHALL provision `deep-research` Agent files only at
`{DEER_FLOW_HOME}/users/{effective_user}/agents/deep-research/`, reference the public
skill and control tool group, and use the dedicated Agent only as a recommended UX
route. Its change-01 SOUL/config guidance SHALL preserve and surface
`implementation_mode=full_fake` and SHALL forbid presenting fake terminal state as
research output. Offline filesystem configuration SHALL provision only explicit no-auth
user `default`; authenticated provisioning SHALL use current-user `POST /api/agents`
only when the operator has independently enabled `agents_api.enabled`. Change 01 SHALL
NOT enable that security-sensitive API automatically. The global control tool SHALL
remain usable when the Agent is absent.

#### Scenario: No-auth user is isolated
- **WHEN** configure provisions an explicit non-production `DEER_FLOW_AUTH_DISABLED=1` installation
- **THEN** it writes the Agent under `users/default/agents/deep-research/` and writes nothing under the shared legacy Agent root

#### Scenario: Production cannot use offline auth-disabled provisioning
- **WHEN** auth-disabled provisioning is requested with `DEER_FLOW_ENV` or `ENVIRONMENT` set to production
- **THEN** configure refuses the Agent write and does not weaken or bypass DeerFlow authentication

#### Scenario: Unvalidated authenticated identity is refused
- **WHEN** offline configuration receives an arbitrary `--user-id` or runs for an authenticated deployment without current-user API attribution
- **THEN** filesystem provisioning fails without creating or modifying any user's Agent directory and directs the authenticated user to the current-user API

#### Scenario: Offline rollback does not own authenticated Agent state
- **WHEN** an authenticated user created the Agent through `POST /api/agents` and an operator rolls back the offline configuration manifest
- **THEN** rollback leaves that user's Agent untouched and directs user-owned deletion through the authenticated Agent API

#### Scenario: Dedicated Agent preserves skeleton honesty
- **WHEN** the dedicated Agent invokes or explains a change-01 lifecycle action
- **THEN** it surfaces the `full_fake` mode, does not claim exclusive tool isolation, and does not describe the terminal fixture as a real research answer or report
