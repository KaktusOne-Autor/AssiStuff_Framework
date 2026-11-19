# ADR-0018: PUPC account registry

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

PUPC needs a stable principal to authorize actions. The current runtime uses
the selected profile name as a `User`, which conflates account identity with
profile-scoped memory and does not authenticate a person.

## Decision

- Add a local account registry separate from profile storage and PUPC policy.
- Represent each account with a stable identifier, display name, status, and
  authentication reference. Accounts may own or select profiles; profile names
  are not credentials and do not determine identity.
- Resolve each active session to one authenticated account and one selected
  profile. Unauthenticated or invalid sessions receive guest-level access.
- Resolve effective access through PUPC policy. Model, skill, plugin, and
  request payloads cannot select or raise the principal's level.
- Require administrator authorization for account and permission changes;
  audit account changes, access changes, and denials without recording
  credentials or prompts.
- Fail closed on missing identity or registry errors. Do not silently fall
  back to a previously authenticated account.
- Keep authentication backends replaceable. The first implementation is
  local; federation and hosted account services require separate explicit
  decisions.

## Consequences

- Add account lifecycle, session, and profile-binding APIs plus account UI.
- Define credential storage and migration from existing `profile_levels`
  before implementation. Migration must not raise effective permissions.
- Apply PUPC checks to every capability and privileged UI action using the
  session principal.
- Wire or remove currently unused confirmation settings; configuration alone
  must not imply a functioning confirmation prompt.

## Implementation status

The local SQLite registry, salted PBKDF2 password authentication, profile
binding, first-account administrator bootstrap, account-management CLI, GUI
sign-in, and dispatcher session refresh are implemented. Account UI,
recovery/MFA, rate limiting, and profile reassignment remain unfinished.
See [account-registry.md](../account-registry.md).
