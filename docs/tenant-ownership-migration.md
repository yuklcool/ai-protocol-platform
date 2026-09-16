# First-class tenant ownership migration

This runbook migrates legacy domain-based ownership into stable first-class
`tenant_id` ownership without guessing from email addresses.

## What the migration changes

`backend/scripts/migrate_tenants.py` can migrate these trusted relationships:

- `clients/{domain}` -> `tenants/{tenant_id}`
- `tenant_domains/{domain}` -> `tenant_id`
- local `auth_users.tenantId` when the account has no explicit tenant yet
- `tenant-admin:{domain}` local-user tags -> `tenant-admin:{tenant_id}`
- legacy domain tool permissions -> `tool_permissions/tenant:{tenant_id}`
- exact local-user tool permission ownership -> `tenantId`
- historical admin audit `tenantId` only when target ownership is explicit

It deliberately does **not** assign ownership from `actorEmail`, an arbitrary
user email address, or other heuristic identifiers. Historical rows that cannot
be attributed from trusted target evidence remain platform-only.

## Tool permission precedence during migration

Runtime resolution is:

```text
user-specific rule
      ↓
tenant:<tenant_id>
      ↓
legacy domain rule
      ↓
wildcard
      ↓
deny
```

The legacy domain rung remains as a compatibility bridge. Once a stable tenant
rule exists, it shadows the domain rule for authenticated requests bound to that
stable tenant.

## Before applying

1. Take a database backup using your normal PostgreSQL/Firestore backup process.
2. Decide the authoritative domain -> tenant mapping outside the migration tool.
3. Prefer stable opaque tenant ids such as `tenant-acme`; do not rely on an email
   domain as the long-term primary key.
4. Run with `--require-explicit` in production so an unmapped legacy domain
   fails rather than silently becoming its own tenant.
5. Review conflicts. The migration fails closed when:
   - two domains merged into one tenant disagree on legacy tenant config;
   - their domain tool permissions differ;
   - a first-class tenant/domain mapping already contains different data;
   - an existing user tool rule claims a tenant different from the exact local
     auth user's explicit assignment.

## Dry run

```bash
cd backend
uv run python scripts/migrate_tenants.py \
  --map acme.com=tenant-acme \
  --map acme-energy.example=tenant-acme \
  --require-explicit
```

Dry-run performs no writes and creates no migration journal.

## Apply

After reviewing the dry-run and taking a backup:

```bash
cd backend
uv run python scripts/migrate_tenants.py \
  --map acme.com=tenant-acme \
  --map acme-energy.example=tenant-acme \
  --require-explicit \
  --apply
```

The command prints a **migration run id**. Keep it with the deployment/change
record.

Each apply writes:

- `tenant_migration_runs/{run_id}`
- `tenant_migration_operations/{run_id}:{sequence}`

For existing records, journal entries contain only fields touched by the
migration and their before/after values. Whole `auth_users` records are never
snapshotted, so password hashes are not copied into migration history.

## Verify after apply

Check at least:

1. every migrated domain resolves to the expected `tenant_id`;
2. local JWT users authenticate with the expected stable tenant;
3. `tenant-admin:<tenant_id>` authority still works;
4. `tool_permissions/tenant:<tenant_id>` reflects the reviewed legacy rules;
5. user-specific permissions still override tenant permissions;
6. Tenant A cannot read or use Tenant B tool permissions;
7. unattributed historical audit rows are still visible only to platform admins;
8. tenant-scoped audit rows are visible only in their target tenant scope.

Do not delete legacy `clients/{domain}` or domain tool-permission rows as part of
this migration. They remain compatibility/rollback inputs until the later
first-class tenant UI and production E2E are fully accepted.

## Rollback

Rollback is available by run id:

```bash
cd backend
uv run python scripts/migrate_tenants.py --rollback <run-id>
```

Rollback performs a full drift preflight before changing anything. If any
migrated document/field no longer matches the migration's recorded after-state,
rollback stops without mutating other operations. This protects legitimate
post-migration edits from being overwritten.

When there is no drift, rollback:

- deletes documents created by the migration;
- restores only fields changed on pre-existing records;
- preserves unrelated fields, including current password hashes and identity
  metadata that were never journaled.

The migration journal is retained and the run is marked `rolled_back`.

## External identity providers

This script can safely rewrite only local JWT identities stored in
`auth_users`. Firebase/OIDC tenant claims and external admin grants must be
migrated at their authoritative identity provider. Do not create local inferred
ownership merely to make the migration appear complete.

## Completion boundary for issue #9

A successful migration is necessary but not sufficient to close #9. Perform a
real Tenant A / Tenant B E2E after migration and verify isolation for:

- Session / Memory
- documents and artifacts
- private Skill configuration
- MCP registry/proxy
- Admin Audit
- quota/budget identity
- Model whitelist/default
- tool permissions

Only after that E2E should the legacy domain compatibility path be considered
for removal.
