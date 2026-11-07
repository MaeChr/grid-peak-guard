# Issue triage

Applies to all issues. Answer in the reporter's language (German or English).

## Priorities

| Label | Meaning | Examples | Target |
|---|---|---|---|
| `P0` | Safety or control error | device not restored after window end, protection time ignored, real service calls in simulation mode | fix immediately, hotfix release |
| `P1` | Core function broken | wrong projection, no escalation, setup fails, crash on start | next release |
| `P2` | Limited function / workaround exists | wrong unit handling for one sensor, translation missing, profile suggestion wrong | planned |
| `P3` | Wish / cosmetic | new device profile, new language, docs | when time allows |

## Labels

- Type: `bug`, `enhancement`, `device-profile`, `documentation`, `question`
- Status: `needs-info`, `confirmed`, `in-progress`, `wontfix`, `duplicate`

## Procedure

1. Check for duplicates; close with `duplicate` and a link.
2. Assign type and priority labels.
3. Missing information (HA version, integration version, diagnostics, logs): label `needs-info` and ask specifically.
4. `needs-info`: reminder after 14 days without answer, close after 28 days (can be reopened).
5. Device profile requests with entity IDs and values → create the JSON profile in a pull request.
6. Never ask for or repeat tokens, passwords or `secrets.yaml` content; ask reporters to redact them.

Automated triage may label, comment and open pull requests, but never merge or release.
