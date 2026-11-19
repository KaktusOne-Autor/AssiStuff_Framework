# Account registry and PUPC

> **Implemented foundation:** local accounts, password authentication, profile
> binding, PUPC levels, account-management CLI, and GUI sign-in are available.
> Profile reassignment, password recovery, MFA, and GUI account administration
> remain unfinished.

## Purpose

The account registry will provide stable local principals for PUPC, the
framework's permission-control layer. An account is an authenticated identity;
a profile is a personal workspace for preferences and memory. They must not be
treated as interchangeable:

- One account may own or select one or more profiles.
- Profiles do not grant privilege. PUPC resolves an authenticated account to
  its effective access level and policy.
- Without an authenticated account, the runtime uses an explicitly limited
  guest identity at level 0.
- A model, skill, plugin, profile name, or request payload cannot assert or
  increase a user's access level.

## Registry responsibilities

The registry is responsible for:

1. Creating, listing, disabling, and deleting local accounts.
2. Binding accounts to profiles and recording the active account/profile
   session.
3. Resolving each session to a stable account ID, display name, and PUPC
   policy level.
4. Requiring an administrator-level principal for account and permission
   changes.
5. Auditing account lifecycle events, permission changes, and denied actions
   without logging passwords, tokens, or request contents.

Authentication credentials must never be stored as plaintext. The first
implementation should use a platform credential store or a well-reviewed
password-hashing scheme; federated identity and remote account services are
separate, explicit integrations. A missing or invalid session must fail closed
to guest access rather than inheriting the last account's authority.

## PUPC enforcement

PUPC remains the authorization policy layer, not the identity provider. It
maps an account to a level and enforces the minimum level declared by a model,
skill, or action. Every capability invocation must preserve the same principal
and check both the caller's permission and the target's access requirements.
Denials are final unless a future, explicit confirmation flow is enabled.

The account UI should expose the current principal, active profile, effective
level, and why an operation was denied. Permission changes must take effect
immediately for new requests and must not silently elevate existing sessions.

## Current implementation

The registry is stored in `~/.assistuff/accounts.db` (or the configured user
data root). Passwords are PBKDF2-HMAC-SHA256 hashes with per-account salts;
the database file is created with owner-only permissions. The first locally
created account becomes the level-5 administrator. Later account creation,
listing, level changes, and disabling require an authenticated administrator.
The last enabled administrator cannot be disabled or demoted.

Use the CLI to bootstrap and administer accounts:

```bash
./bin/assistuff --account-create owner
./bin/assistuff --account-create guest1 --admin-account owner --profile guest1
./bin/assistuff --account-list --admin-account owner
./bin/assistuff --account-set-level <ACCOUNT_ID>:2 --admin-account owner
./bin/assistuff --account-disable <ACCOUNT_ID> --admin-account owner
```

Passwords are entered through a hidden prompt, never command-line arguments.
The GUI requests sign-in at startup when accounts exist. CLI requests use
`--account USERNAME`; account/profile ownership is checked before profile
access. Unauthenticated requests are level-0 guests, isolated to the reserved
`guest` profile when an account registry exists. The dispatcher refreshes the
account's enabled state and PUPC level for each capability call, failing
closed if the account is disabled or no longer owns the selected profile.

The registry currently creates one profile binding per account through the
CLI. Existing `AccessConfig.profile_levels` values are not authentication and
do not elevate a guest. Confirmation-related fields remain configuration,
not a completed confirmation workflow. Account deletion, profile reassignment,
credential recovery, lockout/rate limiting, MFA, and in-GUI account
administration remain unfinished. When accounts exist, model unloading and
`.nrdpkg` installation/removal also require an authenticated level-5
administrator through the AssiStuff and `assistuff-pack` CLIs.

See [ADR-0018](./adr/ADR-0018-pupc-account-registry.md).
