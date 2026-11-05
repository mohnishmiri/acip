# Authentication and authorisation

ACIP uses **two separate identities**:

| Identity | Who | Purpose |
|---|---|---|
| Collection service principal (existing) | backend API + worker | Read Azure Cost Management, export storage, (optionally) Advisor / Activity Log. See `docs/azure-integration.md`. |
| Application users | people using the dashboard | Sign in with Microsoft Entra ID; the SPA calls the ACIP API with a delegated access token. |

The collection identity is never exposed to users, and user tokens are never used to call Azure.

## Modes (`APP_AUTH_MODE`)

- `disabled` — **local development only**. Every request runs as *Local Developer* with the
  administrator role. For testing RBAC, the header `X-ACIP-Dev-Role: viewer|engineering_lead|finops_analyst|administrator`
  downgrades the role, and `X-ACIP-Dev-Application: <application id>` restricts the user to one
  application's subscriptions. The UI exposes the role switch in the user menu (stored in
  `localStorage`, key `acip.devRole`). Never use this mode outside a developer machine.
- `entra` — staging / production.

## Entra app registrations

1. **ACIP API** (e.g. "ACIP API")
   - Expose an API: Application ID URI `api://<api-client-id>`, scope `access_as_user`.
   - Manifest: `"requestedAccessTokenVersion": 2` (the API validates the v2 issuer
     `https://login.microsoftonline.com/<tenant>/v2.0`).
   - App roles (allowed member types: Users/Groups):

     | Value | Display | Role code | Permissions |
     |---|---|---|---|
     | `ACIP.Administrator` | Administrator | `administrator` | read, export, manage_budgets, manage_anomalies, manage_savings, manage_alerts, admin, ingestion |
     | `ACIP.FinOpsAnalyst` | FinOps Analyst | `finops_analyst` | read, export, manage_budgets, manage_anomalies, manage_savings, manage_alerts |
     | `ACIP.EngineeringLead` | Engineering Lead | `engineering_lead` | read, export, manage_anomalies, manage_savings |
     | `ACIP.Viewer` | Read-only Viewer | `viewer` | read, export |

   - Enterprise application → *Assignment required = Yes*; assign users/groups to app roles.
2. **ACIP SPA** (e.g. "ACIP Web")
   - Platform: Single-page application; redirect URI `https://<host>` (and `http://localhost:3000` for dev).
   - API permissions: delegated `api://<api-client-id>/access_as_user`, admin consent.
   - No client secret (public client, authorisation code + PKCE via MSAL).

Configuration (`ConfigMap` / `.env`):

| Variable | Value |
|---|---|
| `APP_AUTH_MODE` | `entra` |
| `ENTRA_TENANT_ID` | tenant GUID |
| `ENTRA_API_CLIENT_ID` | API app registration client id |
| `ENTRA_API_AUDIENCE` | optional; defaults to `api://<ENTRA_API_CLIENT_ID>` |
| `ENTRA_SPA_CLIENT_ID` | SPA app registration client id |
| `ENTRA_API_SCOPE` | `api://<api-client-id>/access_as_user` |

The SPA reads these at runtime from `GET /api/v1/meta/client-config` (public, no secrets), so the
same frontend image is used in every environment.

## Token validation (`app/security/auth.py`)

- RS256 signature against the tenant JWKS (`/<tenant>/discovery/v2.0/keys`, cached 1 h).
- `aud` ∈ {`ENTRA_API_AUDIENCE` or `api://<client id>`, `<client id>`}; `iss` = v2 issuer; `exp`,
  `iat` required; `tid` must equal the configured tenant.
- The user is upserted into `users` (Entra `oid`) on each request.
- Roles = token `roles` claim (mapped through `roles.entra_app_role`) ∪ database assignments.
- No role → HTTP 403 with guidance.

## Subscription-level authorisation

`POST /api/v1/admin/role-assignments` can grant a role scoped to one application
(`application_id`). A user whose grants are *all* application-scoped is restricted to the
subscriptions of those applications: every reporting query receives
`allowed_subscription_fks`, resource/anomaly detail endpoints return 404 outside the scope, and
filter options only list permitted subscriptions. Any unscoped grant (token app role or database
assignment without application) gives access to all subscriptions.

## Audit

State-changing endpoints write `audit_logs` (actor, action, entity, details, client IP):
subscription/application/mapping/rule/setting changes, role assignments, budget changes,
anomaly and savings status, ingestion triggers/retries/reprocess/backfill, connection tests.
Visible under Administration → Audit log (`GET /api/v1/admin/audit-logs`).
