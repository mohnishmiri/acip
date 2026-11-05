# Security

## Principles

- **Read-only towards Azure.** No code path creates, modifies, stops, resizes or deletes Azure
  resources or exports. Savings opportunities are recommendations only.
- **Least privilege.** The collection service principal needs Cost Management Reader (per
  subscription), Storage Blob Data Reader (export storage) and, in AKS, Key Vault Secrets User;
  optional Reader for Advisor / Activity Log. Never Owner or Contributor.
- **Two identities.** The collection service principal (backend only) and user sign-in (Entra ID,
  SPA + API registrations) are separate; user tokens never call Azure, and the collection identity
  is never exposed to the browser.

## Secrets

| Secret | Local | AKS |
|---|---|---|
| Collection identity | `AZURE_CLIENT_SECRET` in git-ignored `.env` | **No secret** — Workload Identity federation of the existing app registration |
| Database URL | `.env` / compose defaults (local only) | Key Vault secret `acip-database-url`, synced by the Secrets Store CSI driver into Secret `<release>-db` |
| TLS certificate | n/a | Kubernetes Secret referenced by the ingress (Key Vault / cert-manager) |

- `.env`, `.env.*` (except `.env.example`), `config/subscriptions.json`, key/certificate files are
  in `.gitignore`. `.env.example` contains placeholders only.
- Secrets are never baked into images (`.dockerignore` excludes `.env*`); `AZURE_CLIENT_SECRET` is a
  `SecretStr` and is never logged or returned (`/azure/connections` reports only
  `client_secret_configured`).
- Azure SDK HTTP logging is set to WARNING to avoid header leakage.

## API protection

- Entra JWT validation (signature, audience, v2 issuer, tenant, expiry) — `app/security/auth.py`.
- RBAC with four roles and per-endpoint permissions; optional application-scoped access that limits
  every query to the user's subscriptions (`allowed_subscription_fks`).
- Input validation with Pydantic models and explicit enumerations (presets, group-by, sort,
  settings values); unknown filters return 422.
- SQL is built with SQLAlchemy Core bound parameters; the only interpolated identifiers come from
  fixed allow-lists (dimension columns, validated week-start integer).
- Standard error envelope without stack traces; correlation via `X-Request-ID`.
- Response headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` (API); frontend adds
  `Referrer-Policy: strict-origin-when-cross-origin` and `Permissions-Policy`.
- CORS limited to `CORS_ORIGINS`. The frontend proxy forwards only an allow-list of headers.
- `APP_AUTH_MODE=disabled` and the `X-ACIP-Dev-*` headers are honoured **only** in disabled mode,
  which must never be used outside a developer machine.

## Audit

`audit_logs` records every state-changing action (who, what, entity, details, client IP);
`ingestion_audit_logs` records worker operations; every billing row keeps its source file,
export run, row number and normaliser version.

## Transport and data

- HTTPS at the ingress (TLS secret); PostgreSQL with `require_secure_transport=ON` and
  `sslmode=require`; Storage and Key Vault via HTTPS only (TLS 1.2+, shared-key access disabled
  on the export storage account).
- Containers run as non-root (uid 10001), read-only root filesystem, no privilege escalation,
  all capabilities dropped, `RuntimeDefault` seccomp; NetworkPolicies isolate ingress in prod.
- Frontend charts escape every string rendered into HTML tooltips (`escapeHtml` in
  `frontend/lib/format.ts`), since tag values and resource names can be user-controlled.
- Demo data is synthetic and labelled (`is_demo`, DEMO banner, export context rows).

## Dependency risk register

| Package | Version | Finding | Severity | Exposure / mitigation | Follow-up |
|---|---|---|---|---|---|
| `postcss` (bundled by `next` 15.5.29) | ≤ 8.5.22 | Path traversal / `.map` file disclosure via attacker-controlled `sourceMappingURL`; XSS in stringify output | High | Build-time only; ACIP builds only its own CSS — no untrusted CSS is processed | Upgrade to Next 16 (major) |
| `echarts` | 5.6.0 | XSS (GHSA-fgmj-fm8m-jvvx) | Moderate | All tooltip/label text passed through `escapeHtml`; no raw HTML from data | Upgrade to ECharts 6.1 (major) |
| `@typescript-eslint/*`, `minimatch` | dev only | ReDoS / glob amplification | Moderate | Developer tooling only, not shipped | Update with the Next 16 lint toolchain |
| `zod` | 4.6.7 | (resolved) memory exhaustion validating oversized collections in < 4.6.6 | High → fixed | Upgraded from 3.25.76 with `@hookform/resolvers` 5 | — |
| `@playwright/test` | 1.64.1 | (resolved) browser download without TLS verification in < 1.55.1 | High → fixed | Upgraded from 1.55.0 | — |

Run `npm audit` (frontend) and `pip-audit` (backend, optional) in CI before releases; the CI
workflow builds images so they can be scanned by Microsoft Defender for Containers / ACR.
